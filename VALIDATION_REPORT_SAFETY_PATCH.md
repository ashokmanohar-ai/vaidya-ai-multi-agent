# VAIDYA AI — Safety patch validation record

**Date:** 18 October 2026

The package was constructed from the previously shared `VAIDYA_AI_Sarvam_Saaras_V4_Updated_2026-10-18.zip`. The original user's large `vaidya-ai-main.zip` was inspected as context but not included, because it contains `.env`, a Windows virtual environment, and local cache/runtime files.

## Verified in build environment

- Offline unit tests: **80 passed, 4 skipped** (`python -m pytest -q tests production_tests`).
- Ten clinical-safety regression tests passed, covering patient-name/age mismatches, matching contexts, malformed dates, ambiguous/reversed negation, Tamil script preservation, referral edit separation, document section headings, DOCX content, and SQLite schema migration.
- Native Python syntax compile completed for modified modules.
- Jinja template parsed without syntax error.
- A synthetic DOCX was generated and rendered to a 2-page PDF/PNG set. Pages were reviewed for layout defects.
- Sarvam adapter mocked SDK lifecycle tests passed; code is aligned with current `create_job()`, `wait_until_complete()` and `download_outputs()` documentation.

## Not verified / must be run on target PC

- Real Flask + LangGraph end-to-end: dependencies could not be installed here because package-index network DNS is unavailable. They account for environment-dependent skipped tests.
- Live Sarvam transcription and its billing/API quota, and true model output quality.
- AWS Bedrock credentials and model availability in your region.
- Full Windows runtime, browser microphone, file uploads and app security/deployment hardening.
- Clinical correctness or permission to use real patient data. **This is not a production-clinical sign-off.**

On Windows, run `python scripts/validate_complete.py` to execute the stricter integration gate, and test only approved synthetic speech samples.
