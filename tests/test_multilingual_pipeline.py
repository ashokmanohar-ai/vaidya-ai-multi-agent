"""Executable tests for audio validation, CPU ASR contracts and Bedrock translation with fake transport.
No AWS credentials or real patient data are used.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from vaidya.audio import FasterWhisperTranscriber
from vaidya.media import save_voice_notes, _audio_extension
from vaidya.translation import BedrockTranslationProvider,PassthroughTranslator
from vaidya.database import Database

class FakeUpload:
    filename='synthetic.wav'
    def __init__(self,payload):self.file=io.BytesIO(payload)
    def read(self,n=-1):return self.file.read(n)

WAV=b'RIFF'+(40).to_bytes(4,'little')+b'WAVEfmt '+b'\x00'*32

def test_magic_detection_and_private_storage(tmp_path):
    refs=save_voice_notes([FakeUpload(WAV)],tmp_path,'abc')
    assert len(refs)==1 and refs[0].endswith('.wav')
    assert Path(refs[0]).read_bytes()==WAV
    assert tmp_path/'audio' in Path(refs[0]).parents
    assert _audio_extension(b'Not a media file') is None


def test_unsupported_audio_rejected(tmp_path):
    with pytest.raises(ValueError,match='Unsupported'):
        save_voice_notes([FakeUpload(b'NOT-WAV-AUDIO'+b'A'*25)],tmp_path,'abc')
    assert not list((tmp_path/'audio').iterdir())


def test_audio_limit_validation(tmp_path):
    with pytest.raises(ValueError,match='Maximum five'):
        save_voice_notes([FakeUpload(WAV) for _ in range(6)],tmp_path,'abc')

class FakeWhisper:
    def __init__(self):self.calls=[]
    def transcribe(self,path,**kwargs):
        self.calls.append((path,kwargs))
        return iter([SimpleNamespace(text='Tamil and English synthetic finding',start=0,end=3)]),SimpleNamespace(language='ta')


def test_cpu_asr_preserves_note_order(tmp_path):
    refs=save_voice_notes([FakeUpload(WAV),FakeUpload(WAV)],tmp_path,'job-x')
    fake=FakeWhisper()
    result=FasterWhisperTranscriber(model='base',engine=fake).transcribe(refs)
    assert [s['note_index'] for s in result.segments]==[0,1]
    assert result.detected_languages==['ta','ta']
    assert len(result.text)>20 and len(fake.calls)==2
    assert all(call[1]['condition_on_previous_text'] is False for call in fake.calls)


def test_passthrough_explicitly_warns():
    result=PassthroughTranslator().translate('தமிழ் English','ta-en')
    assert result.text=='தமிழ் English'
    assert result.provider=='passthrough'
    assert 'No translation performed' in result.warnings[0]

class FakeBedrock:
    def __init__(self):self.payload=None
    def converse(self,**kwargs):
        self.payload=kwargs
        return {'output':{'message':{'content':[{'text':json.dumps({
            'translation':'Synthetic appendix specimen. No fever.',
            'uncertainties':['Check source terminology']})}]}},
            'usage':{'inputTokens':27,'outputTokens':15}}


def test_translation_uses_bedrock_with_explicit_optin(monkeypatch):
    monkeypatch.setenv('AWS_REGION','ap-south-1')
    monkeypatch.setenv('BEDROCK_MODELS','in.openai.gpt-5.6-luna')
    monkeypatch.setenv('LLM_TRANSLATION_MODEL','in.openai.gpt-5.6-luna')
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT','true')
    client=FakeBedrock()
    out=BedrockTranslationProvider(client=client).translate('பரிசோதனை synthetic','ta-en')
    assert out.provider=='aws-bedrock-translation' and out.input_tokens==27
    assert out.text=='Synthetic appendix specimen. No fever.'
    assert client.payload['modelId']=='in.openai.gpt-5.6-luna'
    assert 'Do not add interpretations' in client.payload['system'][0]['text']


def test_translation_refuses_remote_without_optin(monkeypatch):
    monkeypatch.delenv('ALLOW_REMOTE_SYNTHETIC_INPUT',raising=False)
    with pytest.raises(PermissionError):
        BedrockTranslationProvider(client=FakeBedrock()).translate('synthetic','ta-en')


def test_schema_has_media_provenance(tmp_path):
    db=Database(tmp_path/'sqlite.db');db.seed_demo()
    names=[r['name'] for r in db.query('PRAGMA table_info(job_inputs)')]
    assert {'private_ref','metadata_json','kind','seq','job_id'} <= set(names)
