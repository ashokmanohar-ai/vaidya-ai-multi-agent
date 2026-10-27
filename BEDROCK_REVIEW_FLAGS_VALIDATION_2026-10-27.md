# VAIDYA AI — Review flags compatibility validation (27 October 2026)

## Root cause

A Bedrock Converse model response contained five JSON objects such as
`{"text": "The phrase appendix type is unclear."}` under `review_flags`,
where `ReportExtractionSchema` requires a list of strings. The model provided
warnings but packaged them in the wrong shape. This produced a Pydantic
`string_type` error and aborted LangGraph extraction.

## Fixed

- The expected `review_flags` array still has a string contract.
- The provider recognizes the single safe legacy wrapper `{"text": "..."}`
  and converts it into a string without changing the warning.
- Other object shapes, missing/non-string values, blank strings, overly long
  warnings, non-array values and malformed findings/instructions are rejected.
- Validation failures raise a sanitized error without printing input_value,
  potentially revealing patient content or model text.
- The system prompt explicitly requests plain review flag strings.
- No synthetic transcripts or mock fallback were introduced in the audio path.

## Evidence from the packaged source

- Offline `python -m pytest -q`: **130 passed, 4 skipped**.
- Python `compileall` including app, packages and scripts: **passed**.
- `python scripts/validate_structured_review.py`: **passed**, produced a
  synthetic example DOCX.
- Clean extraction plus new regressions: **passed**.
- ZIP CRC/integrity and exclusion of runtime credentials: **passed**.

## Not verified

- `python scripts/validate_complete.py` cannot complete here because Flask
  and LangGraph are not installed in the current offline runtime.
- The four skipped tests cover live/framework/database integration cases.
- No actual Sarvam ASR or AWS Bedrock inference was performed. The user's
  failing live request cannot be replayed without the user's runtime,
  private credentials and approved synthetic test data.
- Windows execution and clinically faithful output are not established.

## Windows instructions

1. Stop the running Flask process using **Ctrl+C**.
2. Extract this updated ZIP into a **new** directory.
3. Use a fresh venv created inside that directory to avoid pulling packages
   from earlier builds; follow `BEDROCK_AUTH_FIX_2026-10-27.md` to configure AWS SSO.
4. Install `requirements-dev.txt` and set the existing `.env` settings privately.
5. Run the offline checks and a synthetic-only Bedrock smoke test:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
python -m pytest -q
python scripts\validate_complete.py
aws sso login --profile bedrock
python scripts\bedrock_smoke_test.py --confirm-cost
python scripts\run_real_audio.py
```

The smoke test sends synthetic text to the configured Bedrock model and may
incur a small charge. Confirm `ALLOW_REMOTE_SYNTHETIC_INPUT=true` only for
approved synthetic/de-identified data. A passing test validates the extraction
shape, not pathology accuracy. Original audio and generated findings still
require qualified human verification before any report is approved.
