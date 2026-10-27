"""Contract tests for Bedrock: all network calls are fake, with no AWS charges."""
import json
from unittest.mock import Mock
import pytest

from vaidya.providers import (
    BedrockConverseProvider, bedrock_settings, get_provider,
)

SYNTHETIC = 'Specimen: appendix. Dictated finding: acute appendicitis. Please bold appendicitis.'


class FakeBedrock:
    def __init__(self, payload=None, usage=None):
        self.payload = payload or {
            'findings': [{'text': 'Acute appendicitis'}],
            'instructions': [{'instruction': 'bold appendicitis'}],
            'review_flags': []
        }
        self.usage = usage or {'inputTokens': 118, 'outputTokens': 40, 'totalTokens': 158}
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {'output': {'message': {'content': [{'text': json.dumps(self.payload)}]}},
                'usage': self.usage}


def enable(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'bedrock')
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT', 'true')
    monkeypatch.delenv('ALLOW_REMOTE_CLINICAL_INPUT', raising=False)
    monkeypatch.setenv('AWS_REGION', 'ap-south-1')
    monkeypatch.setenv('BEDROCK_MODELS', 'in.openai.gpt-5.6-terra,in.openai.gpt-5.6-luna')
    monkeypatch.setenv('LLM_EXTRACTION_MODEL', 'in.openai.gpt-5.6-terra')
    monkeypatch.delenv('BEDROCK_TEMPERATURE', raising=False)
    monkeypatch.setenv('BEDROCK_STRUCTURED_OUTPUT', 'false')


def test_provider_switch_to_bedrock(monkeypatch):
    enable(monkeypatch)
    provider = get_provider()
    assert isinstance(provider, BedrockConverseProvider)
    assert provider.region == 'ap-south-1'
    assert provider.model == 'in.openai.gpt-5.6-terra'


def test_bedrock_mocked_real_contract_and_metrics(monkeypatch):
    enable(monkeypatch)
    fake = FakeBedrock()
    result = BedrockConverseProvider(client=fake).extract(SYNTHETIC)
    assert result.provider == 'aws-bedrock'
    assert result.model == 'in.openai.gpt-5.6-terra'
    assert result.usage['inputTokens'] == 118
    assert result.usage['outputTokens'] == 40
    assert result.latency_ms >= 0
    assert len(result.findings) == 1
    assert 'doctor review' in ' '.join(result.review_flags).lower()
    sent = fake.calls[0]
    assert sent['modelId'] == 'in.openai.gpt-5.6-terra'
    assert sent['inferenceConfig']['maxTokens'] == 1800
    assert 'temperature' not in sent['inferenceConfig']
    assert 'outputConfig' not in sent
    assert '<dictation>' in sent['messages'][0]['content'][0]['text']
    assert len(sent['system']) == 1


def test_json_schema_opt_in(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('BEDROCK_STRUCTURED_OUTPUT', 'true')
    fake = FakeBedrock()
    BedrockConverseProvider(client=fake).extract(SYNTHETIC)
    sent = fake.calls[0]
    fmt = sent['outputConfig']['textFormat']
    assert fmt['type'] == 'json_schema'
    schema = json.loads(fmt['structure']['jsonSchema']['schema'])
    assert schema['required'] == ['findings', 'instructions', 'review_flags']
    assert sent['additionalModelRequestFields']['text']['format']['strict'] is True


def test_allowlisted_model_switch(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('LLM_EXTRACTION_MODEL', 'in.openai.gpt-5.6-luna')
    assert BedrockConverseProvider(client=FakeBedrock()).model.endswith('luna')
    monkeypatch.setenv('LLM_EXTRACTION_MODEL', 'global.anthropic.claude-sonnet-5')
    with pytest.raises(ValueError, match='allowlist'):
        get_provider()


def test_remote_processing_requires_opt_in(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT', 'false')
    fake = FakeBedrock()
    with pytest.raises(RuntimeError, match='disabled'):
        BedrockConverseProvider(client=fake).extract(SYNTHETIC)
    assert fake.calls == []


def test_invalid_model_response_rejected(monkeypatch):
    enable(monkeypatch)
    for payload in ({'findings': 'oops', 'instructions': [], 'review_flags': []},
                    {'findings': ['oops'], 'instructions': [], 'review_flags': []},
                    {'findings': [], 'instructions': [], 'review_flags': [5]},
                    {'findings': [], 'instructions': [{}], 'review_flags': []}):
        with pytest.raises(ValueError):
            BedrockConverseProvider(client=FakeBedrock(payload=payload)).extract(SYNTHETIC)


def test_token_secrecy_in_configuration(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'DO_NOT_PRINT_SECRET_123')
    config = bedrock_settings()
    assert config['credential_configured'] is True
    assert 'DO_NOT_PRINT_SECRET_123' not in str(config)


def test_sdk_config_timeout_and_no_token_argument(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'unused-test-token')
    fake = FakeBedrock()
    spy = Mock(return_value=fake)
    monkeypatch.setattr('boto3.client', spy)
    p = BedrockConverseProvider()
    p.extract(SYNTHETIC)
    args, kwargs = spy.call_args
    assert args == ('bedrock-runtime',)
    assert kwargs['region_name'] == 'ap-south-1'
    assert kwargs['config'].connect_timeout == 8
    assert kwargs['config'].read_timeout == 60
    assert 'aws_secret_access_key' not in kwargs
    assert 'aws_access_key_id' not in kwargs
    assert 'AWS_BEARER_TOKEN_BEDROCK' not in kwargs
