"""Offline, deterministic Sarvam SDK-contract tests. Never calls the paid API."""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from vaidya.audio import SarvamBatchTranscriber, sarvam_keyterms, transcriber, asr_status


class FakeJob:
    def __init__(self, ident, *, state='Completed', transcript='No atypical cells. இணைக்கவும்',
                 language='ta-IN', output_count=1):
        self.job_id = f'job_{ident}'
        self.transcript = transcript
        self.language = language
        self.state = state
        self.output_count = output_count
        self.calls = []

    def upload_files(self, *, file_paths):
        self.calls.append(('upload', file_paths))

    def start(self):
        self.calls.append(('start', None))

    def wait_until_complete(self, *, poll_interval, timeout):
        self.calls.append(('wait', (poll_interval, timeout)))
        return SimpleNamespace(job_state=self.state)

    def download_outputs(self, *, output_dir):
        self.calls.append(('download', output_dir))
        for i in range(self.output_count):
            Path(output_dir, f'{i}.json').write_text(json.dumps({
                'transcript':self.transcript, 'language_code':self.language,
                'timestamps':{'chunks':['No atypical cells.', 'இணைக்கவும்'],
                              'start_time_seconds':[0,2.5], 'end_time_seconds':[2.2,3.0]},
            }), encoding='utf-8')


class FakeSarvam:
    def __init__(self, **kwargs):
        self.created = []
        self.params = []
        self.config = kwargs
        self.speech_to_text_job = self

    def create_job(self, **kwargs):
        self.params.append(kwargs)
        ident=len(self.created)
        job=FakeJob(ident, **self.config)
        self.created.append(job)
        return job


def sample_files(tmp_path, number=1):
    files=[]
    for i in range(number):
        p=tmp_path/f'voice{i}.ogg'
        p.write_bytes(b'OggSsynthetic-voice-'+str(i).encode())
        files.append(str(p))
    return files


def test_sarvam_batch_create_upload_start_wait_download_preserves_unicode(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    monkeypatch.delenv('SARVAM_KEYTERMS', raising=False)
    fake=FakeSarvam()
    files=sample_files(tmp_path,2)
    output=SarvamBatchTranscriber(client=fake).transcribe(files)
    assert output.provider=='sarvam' and output.model=='saaras:v4' and output.mode=='codemix'
    assert output.detected_languages == ['ta-IN','ta-IN']
    assert len(fake.created)==2 and output.job_ids==['job_0','job_1']
    assert output.text.count('இணைக்கவும்')==2
    assert [x['note_index'] for x in output.segments]==[0,0,1,1]
    assert [j.calls[0][1][0] for j in fake.created]==files
    assert all([call[0] for call in j.calls]==['upload','start','wait','download'] for j in fake.created)
    assert fake.params[0]['model']=='saaras:v4'
    assert fake.params[0]['mode']=='codemix'
    assert fake.params[0]['language_code']=='unknown'
    assert fake.params[0]['with_timestamps'] is True
    assert 'neutrophils' in fake.params[0]['keyterms']


def test_force_tamil_and_english(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    fake=FakeSarvam()
    engine=SarvamBatchTranscriber(client=fake)
    engine.transcribe(sample_files(tmp_path), language='ta')
    assert fake.params[0]['language_code']=='ta-IN'
    engine.transcribe(sample_files(tmp_path), language='en')
    assert fake.params[1]['language_code']=='en-IN'


def test_cloud_asr_requires_explicit_synthetic_approval(tmp_path,monkeypatch):
    monkeypatch.delenv('ALLOW_REMOTE_SYNTHETIC_INPUT',raising=False)
    fake=FakeSarvam()
    with pytest.raises(PermissionError,match='transmission approval'):
        SarvamBatchTranscriber(client=fake).transcribe(sample_files(tmp_path))
    assert fake.created==[]


def test_missing_key_does_not_call_network(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    monkeypatch.delenv('SARVAM_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='SARVAM_API_KEY'):
        SarvamBatchTranscriber().transcribe(sample_files(tmp_path))


def test_failed_or_partial_job_refuses_transcript(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    for state in ['Failed','PartiallyCompleted','Running']:
        fake=FakeSarvam(state=state)
        with pytest.raises(RuntimeError,match='not completed'):
            SarvamBatchTranscriber(client=fake).transcribe(sample_files(tmp_path))
        assert not any(c[0]=='download' for c in fake.created[0].calls)


def test_multiple_output_files_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    fake=FakeSarvam(output_count=2)
    with pytest.raises(RuntimeError,match='exactly one'):
        SarvamBatchTranscriber(client=fake).transcribe(sample_files(tmp_path))


def test_keyterm_validation_and_defaults(monkeypatch):
    monkeypatch.delenv('SARVAM_KEYTERMS',raising=False)
    assert 'acute appendicitis' in sarvam_keyterms()
    for value in ['"notalist"', '"broken', json.dumps(['same','same']), json.dumps(['x'*65]), json.dumps(['x']*51)]:
        monkeypatch.setenv('SARVAM_KEYTERMS',value)
        with pytest.raises(ValueError, match='SARVAM_KEYTERMS'):
            sarvam_keyterms()


def test_provider_selection_and_status_do_not_expose_secret(monkeypatch):
    monkeypatch.setenv('ASR_PROVIDER','sarvam')
    monkeypatch.setenv('SARVAM_API_KEY','TEST_SECRET_NOT_FOR_RESPONSE')
    assert isinstance(transcriber(),SarvamBatchTranscriber)
    assert 'TEST_SECRET_NOT_FOR_RESPONSE' not in str(asr_status())
    assert asr_status()['provider']=='sarvam'


def test_empty_output_is_hard_error(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    fake=FakeSarvam(transcript='')
    with pytest.raises(RuntimeError,match='empty transcript'):
        SarvamBatchTranscriber(client=fake).transcribe(sample_files(tmp_path))


def test_temporary_outputs_are_deleted(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    fake=FakeSarvam()
    trans=SarvamBatchTranscriber(client=fake)
    trans.transcribe(sample_files(tmp_path))
    output_dir=fake.created[0].calls[-1][1]
    assert not Path(output_dir).exists()
