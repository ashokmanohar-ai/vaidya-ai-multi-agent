# Bedrock review_flags schema drift fix (27 October 2026)

## Reported issue

A successful Bedrock Converse response could return `review_flags` as objects such as
`{"text": "The phrase appendix type is unclear."}` instead of the documented string
array. `ReportExtractionSchema` rejected them and prevented report generation.

## Changes

- Accept **only** a single-field object containing a string `text` for individual
  review flags, alongside the originally supported plain strings. Preserve every
  warning as written; do not remove uncertain or clinically important content.
- Reject extra dictionary fields, missing/non-string text, non-list collections,
  empty warnings, and excessively long warnings. The parser continues to reject
  malformed findings and instructions, and never substitutes mock outputs.
- Clarify the prompt that each `review_flags` entry must be a plain string.
- Sanitize validation exceptions to prevent echoed transcription/patient text
  entering Flask logs or error pages.
- Add regression tests covering the original five-error case, mixed shapes,
  data preservation, malicious extra fields, overlong values, and error secrecy.

## Testing

Run from the project root:

```powershell
python -m pytest -q
python -m compileall -q vaidya app.py scripts
python scripts/validate_complete.py
```

For a potentially billed **synthetic-only** live Bedrock smoke test, after configuring
`AWS_PROFILE`, SSO and approved model permissions, run:

```powershell
aws sso login --profile bedrock
python scripts/bedrock_smoke_test.py --confirm-cost
```

Restart `scripts/run_real_audio.py` after installing the updated source.

## Limits

- The offline tests use an in-memory fake Bedrock service; live AWS credentials,
  a live Sarvam transcription, and full Windows end-to-end testing were not
  available for this release.
- The fix addresses the observed output **shape mismatch**, not transcription
  accuracy, clinical validation, or identification of missing medical negations.
- Development/synthetic or appropriately de-identified testing only. Do not
  use for real patient decisions or publish an unverified report.
