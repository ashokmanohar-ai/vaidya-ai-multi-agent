# Public source repository — evaluation only

This project demonstrates Tamil–English Sarvam speech-to-text, AWS Bedrock extraction, LangGraph orchestration, and a clinician-review *prototype*. **Not validated for clinical use.**

**No medical data, recordings, scanned pathology reports, generated DOCX documents, access tokens, runtime databases, or environment secrets are included.** Some test fixtures contain intentionally invented patient identities and demonstration accounts; those accounts are **not secure credentials** and must not be enabled outside localhost.

## Getting started

Create a local `.env` from `.env.example` and use `BEDROCK_AUTH_MODE=bearer` plus a private `AWS_BEARER_TOKEN_BEDROCK`, or configure `BEDROCK_AUTH_MODE=profile` with a legitimate AWS profile. Configure your Sarvam credentials and only send approved synthetic or appropriately de-identified evaluation audio.

Follow `START_HERE_WINDOWS.txt`, `REAL_AUDIO_INTEGRATION.md`, and `BEDROCK_REVIEW_FLAGS_FIX_2026-10-27.md`. Test with `python -m pytest -q`.

Known limitations: live Sarvam ASR accuracy and clinical report fidelity are unverified; complete Windows/Flask/LangGraph E2E and paid AWS APIs require separately approved credentials and tests. Refer to the release validation notes for skips and limitations.

## Licensing

No license is granted by default; contact the repository owner before reuse.
