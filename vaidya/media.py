"""Synthetic-only upload validators and private local storage for the CPU pilot."""
from __future__ import annotations
from pathlib import Path
import uuid

MAX_VOICE_FILES=5
MAX_VOICE_BYTES=12 * 1024 * 1024


def _audio_extension(header:bytes)->str|None:
    if header[:4]==b'RIFF' and header[8:12]==b'WAVE':return '.wav'
    if header[:3]==b'ID3' or (len(header)>2 and header[0]==0xff and (header[1]&0xe0)==0xe0):return '.mp3'
    if header[4:8]==b'ftyp':return '.m4a'
    if header[:4]==b'\x1a\x45\xdf\xa3':return '.webm'
    if header[:4]==b'OggS':return '.ogg'
    return None


def save_voice_notes(files, data_dir:Path, job_id:str)->list[str]:
    """Validate audio magic bytes + count + cap, never trust user supplied filename."""
    items=[f for f in files if f is not None and getattr(f,'filename',None)]
    if len(items)>MAX_VOICE_FILES:raise ValueError('Maximum five audio notes allowed')
    results=[];target_dir=Path(data_dir)/'audio';target_dir.mkdir(parents=True,exist_ok=True)
    try:
        for index,f in enumerate(items):
            payload=f.read(MAX_VOICE_BYTES+1)
            if len(payload)>MAX_VOICE_BYTES:raise ValueError('Audio note exceeds 12 MB limit')
            if len(payload)<12:raise ValueError('Audio note too small or unsupported')
            ext=_audio_extension(payload[:32])
            if not ext:raise ValueError('Unsupported audio format; use WAV, MP3, M4A, WebM, or OGG')
            dest=target_dir/f'{job_id}-{index}-{uuid.uuid4().hex[:8]}{ext}'
            dest.write_bytes(payload)
            results.append(str(dest.resolve()))
    except Exception:
        for path in results:Path(path).unlink(missing_ok=True)
        raise
    return results
