"""Credential selection and safe AWS exception handling, without network calls."""
import pytest
from unittest.mock import Mock
from botocore.exceptions import ClientError, NoCredentialsError

from vaidya.providers import BedrockConverseProvider, bedrock_auth_configuration


def clear_auth(monkeypatch):
    for name in ('AWS_PROFILE', 'AWS_BEARER_TOKEN_BEDROCK',
                 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'BEDROCK_AUTH_MODE'):
        monkeypatch.delenv(name, raising=False)


def test_sso_profile_selection(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('BEDROCK_AUTH_MODE', 'profile')
    monkeypatch.setenv('AWS_PROFILE', 'bedrock')
    assert bedrock_auth_configuration() == {'mode': 'profile', 'profile': 'bedrock'}


def test_profile_and_bearer_conflict_rejected(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('BEDROCK_AUTH_MODE', 'profile')
    monkeypatch.setenv('AWS_PROFILE', 'bedrock')
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'TOP_SECRET_TOKEN')
    with pytest.raises(RuntimeError, match='conflicts') as exc:
        bedrock_auth_configuration()
    assert 'TOP_SECRET_TOKEN' not in str(exc.value)


def test_auto_mode_rejects_auth_family_conflicts(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('AWS_PROFILE', 'bedrock')
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'TOKEN')
    with pytest.raises(RuntimeError, match='Conflicting'):
        bedrock_auth_configuration()


def test_bearer_must_not_have_bearer_prefix(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('BEDROCK_AUTH_MODE', 'bearer')
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'Bearer TEST_TOKEN')
    with pytest.raises(RuntimeError, match='without a Bearer prefix'):
        bedrock_auth_configuration()


def test_profile_uses_explicit_boto3_session(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('BEDROCK_AUTH_MODE', 'profile')
    monkeypatch.setenv('AWS_PROFILE', 'bedrock')
    spy_session = Mock()
    spy_session.client.return_value = Mock()
    make_session = Mock(return_value=spy_session)
    monkeypatch.setattr('boto3.Session', make_session)
    client = BedrockConverseProvider(model='in.openai.gpt-5.6-terra')._client()
    assert client is spy_session.client.return_value
    make_session.assert_called_once_with(profile_name='bedrock')
    assert spy_session.client.call_args.args == ('bedrock-runtime',)


def test_invalid_signature_cannot_leak_service_message(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT', 'true')
    fake = Mock()
    fake.converse.side_effect = ClientError(
        {'Error': {'Code': 'IncompleteSignatureException',
                   'Message': 'Authorization=VERY_PRIVATE_BEARER_TOKEN'}}, 'Converse')
    with pytest.raises(RuntimeError, match='IncompleteSignatureException') as exc:
        BedrockConverseProvider(model='in.openai.gpt-5.6-terra', client=fake).extract('synthetic appendix sample')
    assert 'VERY_PRIVATE_BEARER_TOKEN' not in str(exc.value)
    assert exc.value.__cause__ is None


def test_missing_credentials_friendly_failure(monkeypatch):
    clear_auth(monkeypatch)
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT', 'true')
    fake = Mock()
    fake.converse.side_effect = NoCredentialsError()
    with pytest.raises(RuntimeError, match='No AWS Bedrock credentials'):
        BedrockConverseProvider(model='in.openai.gpt-5.6-terra', client=fake).extract('synthetic appendix sample')
