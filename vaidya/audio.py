"""Swappable ASR adapters for the local SYNTHETIC VAIDYA AI pilot.

Audio is untrusted input. Cloud transcription is opt-in, billable, and not
approved for identifiable clinical information. Provider outputs are evidence
for human review, never proof of clinical correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


@dataclass
class Transcription:
    text: str
    segments: list[dict] = field(default_factory=list)
    detected_languages: list[str] = field(default_factory=list)
    provider: str = 'faster-whisper'
    model: str = ''
    mode: str = ''
    job_ids: list[str] = field(default_factory=list)
    audio_sha256: list[str] = field(default_factory=list)
    transcript_sha256: str = ""


class FasterWhisperTranscriber:
    def __init__(self, model=None, engine=None):
        self.model_name = model or os.getenv('WHISPER_MODEL_PATH') or os.getenv('WHISPER_MODEL_SIZE', 'base')
        self.engine = engine

    def _engine(self):
        if self.engine is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError('Install requirements-audio.txt for CPU transcription. No simulated ASR fallback.') from exc
            self.engine = WhisperModel(self.model_name, device='cpu', compute_type='int8',
                                       cpu_threads=min(4, os.cpu_count() or 2))
        return self.engine

    def transcribe(self, files: list[str], language: str | None = None) -> Transcription:
        _validate_files(files)
        pieces, segments, languages = [], [], []
        for index, filename in enumerate(files):
            # The local provider expects 'ta'/'en', not a BCP-47 region code.
            lang = language.split('-', 1)[0] if language else None
            result, info = self._engine().transcribe(str(filename), language=lang, beam_size=3,
                       vad_filter=True, condition_on_previous_text=False)
            detected = getattr(info, 'language', 'und')
            languages.append(detected)
            for segment in result:
                text = segment.text.strip()
                if text:
                    segments.append({'note_index': index, 'start': round(float(segment.start), 2),
                                     'end': round(float(segment.end), 2), 'text': text, 'language': detected})
                    pieces.append(text)
        text = ' '.join(pieces).strip()
        if not text:
            raise RuntimeError('Local ASR returned an empty transcript; no fallback supplied')
        return Transcription(text=text, segments=segments, detected_languages=languages,
                             model=self.model_name,
                             audio_sha256=[file_sha256(Path(f)) for f in files],
                             transcript_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())


def _validate_files(files: list[str]) -> None:
    if not files or len(files) > 5:
        raise ValueError('Between 1 and 5 voice notes required')
    for filename in files:
        path = Path(filename)
        if not path.is_file():
            raise FileNotFoundError('Uploaded voice note not found')
        if path.stat().st_size < 12 or path.stat().st_size > 12 * 1024 * 1024:
            raise ValueError('Audio must be 12 bytes to 12 MB')
        from .media import _audio_extension
        with path.open('rb') as stream:
            header = stream.read(32)
        if _audio_extension(header) is None:
            raise ValueError('Unsupported audio content: expected WAV/MP3/M4A/WebM/OGG')



def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _as_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if hasattr(value, 'dict'):
        return value.dict()
    return {key: getattr(value, key) for key in ('job_state', 'job_id', 'language_code', 'failed_files_count', 'successful_files_count') if hasattr(value, key)}


def _positive_int_setting(name: str, default: int, lo: int, hi: int) -> int:
    try:
        result = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if not lo <= result <= hi:
        raise ValueError(f'{name} must be between {lo} and {hi}')
    return result


DEFAULT_MEDICAL_KEYTERMS = (
    'appendix', 'appendicular mucosa', 'acute appendicitis', 'histopathology',
    'neutrophils', 'lymphocytes', 'plasma cells', 'serosa', 'atypical cells',
    'gross examination', 'microscopy', 'biopsy', 'lumen patent',
)


def sarvam_keyterms() -> list[str]:
    """A list of recognition hints, never clinical assertions to insert."""
    raw = os.getenv('SARVAM_KEYTERMS', '')
    try:
        values = json.loads(raw) if raw.strip() else list(DEFAULT_MEDICAL_KEYTERMS)
    except json.JSONDecodeError as exc:
        raise ValueError('SARVAM_KEYTERMS must be a JSON list') from exc
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise ValueError('SARVAM_KEYTERMS must be a JSON list of strings')
    if len(values) > 50 or len(set(values)) != len(values) or any(not 1 <= len(x.strip()) <= 64 for x in values):
        raise ValueError('SARVAM_KEYTERMS must contain at most 50 distinct terms, 1–64 characters each')
    return values


class SarvamBatchTranscriber:
    """Saaras V4 batch-job SDK integration, preserving note order.

    One batch *job* per note intentionally: Sarvam may name downloaded JSON as
    0.json even when input filenames are arbitrary; per-note jobs avoid any
    possibility of attaching the wrong transcript to another patient/note.
    This synchronous MVP must be moved to a durable queue for deployment.
    """

    def __init__(self, client=None, *, mode: str | None = None, language_code: str | None = None):
        self.client = client
        self.model = 'saaras:v4'
        self.mode = mode or os.getenv('SARVAM_MODE', 'codemix').strip().lower()
        self.language_code = language_code or os.getenv('SARVAM_LANGUAGE_CODE', 'unknown').strip()
        if self.mode not in ('codemix', 'transcribe', 'verbatim', 'translit', 'translate'):
            raise ValueError('Invalid SARVAM_MODE')
        if self.language_code not in ('unknown', 'en-IN', 'ta-IN'):
            raise ValueError('SARVAM_LANGUAGE_CODE must be unknown, en-IN or ta-IN for this pilot')
        self.poll_interval = _positive_int_setting('SARVAM_POLL_INTERVAL_SECONDS', 5, 1, 60)
        self.timeout = _positive_int_setting('SARVAM_JOB_TIMEOUT_SECONDS', 600, 30, 3600)

    def _client(self):
        if self.client is not None:
            return self.client
        key = os.getenv('SARVAM_API_KEY', '').strip()
        if not key:
            raise RuntimeError('SARVAM_API_KEY is missing. Configure it privately in .env.')
        try:
            from sarvamai import SarvamAI
        except ImportError as exc:
            raise RuntimeError('Install requirements-sarvam.txt for cloud ASR.') from exc
        self.client = SarvamAI(api_subscription_key=key)
        return self.client

    @staticmethod
    def _parse_output(path: Path, note_index: int) -> tuple[str, str, list[dict]]:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError('Sarvam transcript JSON exceeds safety limit')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError('Sarvam returned invalid transcript JSON') from exc
        if not isinstance(data, dict) or not isinstance(data.get('transcript'), str):
            raise RuntimeError('Sarvam output has no transcript field')
        text = data['transcript'].strip()
        if not text:
            raise RuntimeError('Sarvam returned an empty transcript; inspect input audio')
        if len(text) > 16000:
            raise RuntimeError('Sarvam transcript exceeds document intake limit')
        language = str(data.get('language_code') or 'und')
        stamps = data.get('timestamps') or {}
        chunks = (stamps.get('words') or stamps.get('chunks') or []) if isinstance(stamps, dict) else []
        starts = stamps.get('start_time_seconds', []) if isinstance(stamps, dict) else []
        ends = stamps.get('end_time_seconds', []) if isinstance(stamps, dict) else []
        segments: list[dict] = []
        if isinstance(chunks, list) and isinstance(starts, list) and isinstance(ends, list):
            for chunk, start, end in zip(chunks[:500], starts[:500], ends[:500]):
                if isinstance(chunk, str) and isinstance(start, (int, float)) and isinstance(end, (int, float)):
                    segments.append({'note_index': note_index, 'text': chunk,
                                    'start': round(float(start), 2), 'end': round(float(end), 2),
                                    'language': language})
        return text, language, segments

    def transcribe(self, files: list[str], language: str | None = None) -> Transcription:
        _validate_files(files)
        # Strong opt-in applies to any cloud audio transmission, including the
        # synthetic pilot. Explicitly *not* permission for real patient data.
        if os.getenv('ALLOW_REMOTE_SYNTHETIC_INPUT', '').lower() != 'true' and os.getenv('VAIDYA_SARVAM_CLINICAL_APPROVED','').lower() != 'true':
            raise PermissionError('Cloud ASR disabled: explicit synthetic or governed clinical transmission approval required')
        code = {'ta': 'ta-IN', 'en': 'en-IN'}.get(language or '', language or self.language_code)
        if code not in ('unknown', 'ta-IN', 'en-IN'):
            raise ValueError('Unsupported Sarvam input language for this pilot')
        keyterms = sarvam_keyterms()
        client = self._client()
        transcript_parts: list[str] = []
        segments: list[dict] = []
        languages: list[str] = []
        job_ids: list[str] = []
        for index, filename in enumerate(files):
            # API follows Sarvam SDK batch example: create → upload → start →
            # wait_until_complete → download_outputs. No data in logs.
            job = client.speech_to_text_job.create_job(
                model=self.model, mode=self.mode, language_code=code,
                keyterms=keyterms, with_timestamps=True,
            )
            job_id = str(getattr(job, 'job_id', '')).strip()
            if not job_id:
                raise RuntimeError('Sarvam job creation failed (missing job ID)')
            job_ids.append(job_id)
            job.upload_files(file_paths=[str(filename)])
            job.start()
            state = _as_mapping(job.wait_until_complete(poll_interval=self.poll_interval, timeout=self.timeout))
            if str(state.get('job_state', '')).lower() != 'completed':
                raise RuntimeError('Sarvam batch job was not completed successfully')
            if state.get('failed_files_count', 0):
                raise RuntimeError('Sarvam batch job reported a failed audio file')
            with TemporaryDirectory(prefix='vaidya-sarvam-') as temporary:
                folder = Path(temporary)
                job.download_outputs(output_dir=str(folder))
                # This single-input job must yield exactly one output; any extra
                # file is ambiguous and is rejected instead of guessed at.
                outputs = sorted(folder.rglob('*.json'))
                if len(outputs) != 1 or not outputs[0].is_file():
                    raise RuntimeError('Expected exactly one Sarvam transcript JSON for each voice note')
                content, detected, note_segments = self._parse_output(outputs[0], index)
            transcript_parts.append(content)
            languages.append(detected)
            segments.extend(note_segments)
        combined = '\n'.join(transcript_parts)
        if len(combined) > 16000:
            raise ValueError('Combined cloud transcript exceeds the maximum input length')
        return Transcription(text=combined, segments=segments, detected_languages=languages,
                             provider='sarvam', model=self.model, mode=self.mode, job_ids=job_ids,
                             audio_sha256=[file_sha256(Path(f)) for f in files],
                             transcript_sha256=hashlib.sha256(combined.encode('utf-8')).hexdigest())


def asr_status() -> dict:
    """Configuration only; safe for health/admin endpoints (never expose keys)."""
    provider = os.getenv('ASR_PROVIDER', 'faster-whisper').strip().lower()
    if provider == 'sarvam':
        try:
            from importlib.util import find_spec
            installed = find_spec('sarvamai') is not None
        except (ImportError, ValueError):
            installed = False
        return {'provider': provider, 'model': 'saaras:v4', 'mode': os.getenv('SARVAM_MODE', 'codemix'),
                'sdk_installed': installed, 'credentials_configured': bool(os.getenv('SARVAM_API_KEY', '').strip()),
                'remote_transmission_approved': os.getenv('ALLOW_REMOTE_SYNTHETIC_INPUT', '').lower() == 'true' or os.getenv('VAIDYA_SARVAM_CLINICAL_APPROVED','').lower() == 'true',
                'ready': installed and bool(os.getenv('SARVAM_API_KEY', '').strip())
                         and (os.getenv('ALLOW_REMOTE_SYNTHETIC_INPUT', '').lower() == 'true' or os.getenv('VAIDYA_SARVAM_CLINICAL_APPROVED','').lower() == 'true')}
    if provider == 'faster-whisper':
        from importlib.util import find_spec
        available = find_spec('faster_whisper') is not None
        return {'provider': provider, 'model': os.getenv('WHISPER_MODEL_SIZE', 'base'),
                'sdk_installed': available, 'credentials_configured': True,
                'remote_synthetic_opt_in': False, 'ready': available}
    return {'provider': provider, 'ready': False}


def transcriber():
    provider = os.getenv('ASR_PROVIDER', 'faster-whisper').strip().lower()
    if provider == 'sarvam':
        return SarvamBatchTranscriber()
    if provider == 'faster-whisper':
        return FasterWhisperTranscriber()
    raise ValueError('Unsupported ASR_PROVIDER. Supported: sarvam, faster-whisper')
