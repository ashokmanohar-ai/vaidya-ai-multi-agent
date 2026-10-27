"""Pure offline ASR provenance and error contracts. No live API, no PHI."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from vaidya.audio import SarvamBatchTranscriber
from scripts.evaluate_transcription import evaluate

class RemoteJob:
    job_id = 'job_test_987'
    def __init__(self, transcript, failure=False):
        self.transcript=transcript
        self.failure=failure
        self.events=[]
    def upload_files(self,*,file_paths):
        self.events.append('upload')
        assert len(file_paths)==1 and Path(file_paths[0]).is_file()
    def start(self):self.events.append('start')
    def wait_until_complete(self,**kwargs):
        self.events.append('wait')
        return SimpleNamespace(job_state='Failed' if self.failure else 'Completed')
    def download_outputs(self,*,output_dir):
        self.events.append('download')
        Path(output_dir,'0.json').write_text(json.dumps({'transcript':self.transcript,
            'language_code':'ta-IN',
            'timestamps':{'words':[self.transcript], 'start_time_seconds':[0.0],
                          'end_time_seconds':[1.5]}}),encoding='utf-8')

class Remote:
    def __init__(self,transcript,failure=False):
        self.speech_to_text_job=self
        self.created=[]
        self.transcript=transcript
        self.failure=failure
    def create_job(self,**params):
        self.created.append(RemoteJob(self.transcript,self.failure))
        return self.created[-1]

def ogg(tmp_path):
    a=tmp_path/'uploaded.ogg'
    a.write_bytes(b'OggS'+b'approved-evaluation-only-payload')
    return a

def test_asr_response_is_exact_cloud_output_with_provenance(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    monkeypatch.delenv('VAIDYA_SARVAM_CLINICAL_APPROVED',raising=False)
    audio=ogg(tmp_path)
    transcript='Appendix five centimetres. நோயாளி சொன்னது.'
    api=Remote(transcript)
    answer=SarvamBatchTranscriber(client=api).transcribe([str(audio)])
    assert answer.text==transcript and answer.provider=='sarvam'
    assert answer.transcript_sha256==hashlib.sha256(transcript.encode('utf8')).hexdigest()
    assert answer.audio_sha256==[hashlib.sha256(audio.read_bytes()).hexdigest()]
    assert answer.segments[0]['text']==transcript
    assert api.created[0].events==['upload','start','wait','download']

def test_failed_api_does_not_create_transcript(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    api=Remote('This is a decoy transcript',failure=True)
    with pytest.raises(RuntimeError,match='not completed'):
        SarvamBatchTranscriber(client=api).transcribe([str(ogg(tmp_path))])
    assert api.created[0].events==['upload','start','wait']

def test_empty_api_output_is_failure(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    with pytest.raises(RuntimeError,match='empty transcript'):
        SarvamBatchTranscriber(client=Remote('  ')).transcribe([str(ogg(tmp_path))])

def test_corrupt_audio_blocks_before_provider_call(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    path=tmp_path/'invalid.ogg';path.write_bytes(b'not a valid media container')
    api=Remote('dummy')
    with pytest.raises(ValueError,match='Unsupported audio content'):
        SarvamBatchTranscriber(client=api).transcribe([str(path)])
    assert api.created==[]

def test_wer_cer_and_clinical_phrase_regression():
    perfect=evaluate('No atypical cells. தமிழ்','No atypical cells. தமிழ்',['No atypical cells'])
    assert perfect['wer']==0 and perfect['cer']==0 and perfect['missing_critical_phrase_count']==0
    bad=evaluate('No atypical cells. தமிழ்','And atypical cells. தமிழ்',['No atypical cells'])
    assert bad['wer']>0 and bad['missing_critical_phrase_count']==1
    with pytest.raises(ValueError):evaluate('hello','')

def test_source_code_disallows_fake_runtime_transcription():
    root=Path(__file__).resolve().parents[1]
    app=(root/'app.py').read_text()
    graph=(root/'vaidya/multi_agent.py').read_text()
    prod=(root/'production/graph.py').read_text()
    assert "if AUDIO_ONLY and transcript:" in app
    assert "if AUDIO_ONLY and not audio_files:" in app
    assert "if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true' and text:" in graph
    assert "if not audios:" in prod
    assert "'asr_provenance.json'" in prod
