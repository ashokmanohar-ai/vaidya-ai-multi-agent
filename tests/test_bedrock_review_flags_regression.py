"""Offline regression coverage for Bedrock's review_flags object-wrapping drift."""
import json
import pytest

from vaidya.providers import BedrockConverseProvider
from vaidya.schemas import ReportExtractionSchema


class FakeConverse:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": json.dumps(self.result)}]}},
                "usage": {"inputTokens": 20, "outputTokens": 35}}


def sample(flags):
    return {"findings": [{"text": "Appendix, measured 5 cm"}],
            "instructions": [], "review_flags": flags}


def provider(monkeypatch, flags):
    monkeypatch.setenv("ALLOW_REMOTE_SYNTHETIC_INPUT", "true")
    monkeypatch.setenv("BEDROCK_STRUCTURED_OUTPUT", "false")
    fake = FakeConverse(sample(flags))
    return BedrockConverseProvider(model="in.openai.gpt-5.6-terra", client=fake), fake


def test_five_review_flag_wrappers_no_longer_fail(monkeypatch):
    exact = ["The phrase appendix type is unclear.",
             "Verify the patient's name.",
             "Verify biopsy number.",
             "Verify date received.",
             "Verify absence of atypical cells against audio."]
    p, fake = provider(monkeypatch, [{"text": item} for item in exact])
    result = p.extract("Synthetic appendix dictation")
    assert fake.calls == 1
    assert result.review_flags[:5] == exact
    assert len(result.review_flags) == 6  # Adds doctor-review warning.
    assert result.findings[0]["text"] == "Appendix, measured 5 cm"


def test_mixed_plain_string_and_single_text_wrapper(monkeypatch):
    p, _ = provider(monkeypatch, ["Verify identity", {"text": "Check missing negation"}])
    assert p.extract("Synthetic input").review_flags[:2] == ["Verify identity", "Check missing negation"]


@pytest.mark.parametrize('flags', [
    [{"text": "Flag", "severity": "high"}],
    [{"message": "Flag"}],
    [{"text": ["Flag"]}],
    [3], [None], [""], [" "], ["x" * 301],
    "not-an-array",
])
def test_unsafe_review_flag_shape_fails_closed_without_fabricating(monkeypatch, flags):
    p, _ = provider(monkeypatch, flags)
    with pytest.raises(ValueError, match="schema validation"):
        p.extract("Synthetic input")


def test_model_output_not_echoed_in_exception(monkeypatch):
    secret = "PRIVATE_PATIENT_IDENTIFIER_987654"
    p, _ = provider(monkeypatch, [{"unknown": secret}])
    with pytest.raises(ValueError) as exc:
        p.extract("Synthetic input")
    assert secret not in str(exc.value)
    assert exc.value.__cause__ is None


def test_schema_remains_strict_and_is_not_changed_to_arbitrary_json():
    schema = ReportExtractionSchema.model_json_schema()
    flags = schema["properties"]["review_flags"]
    assert flags["type"] == "array"
    assert flags["items"]["type"] == "string"
