# VAIDYA AI — Sarvam Batch Integration Test Evidence (2026-10-18)

## What was changed

- New Sarvam Saaras V4 SDK batch transcription adapter using official `speech_to_text_job.create_job`, `upload_files`, `start`, `wait_until_complete`, and `download_outputs` workflow.
- Default `SARVAM_MODE=codemix`, `SARVAM_LANGUAGE_CODE=unknown`, configurable medical keyterms, bounded polling and timeout.
- Supports OGG/Opus via existing magic-byte-validated upload handler. The 30-second REST limit is avoided using batch.
- Source transcript, optional Bedrock-translated version, per-note ASR metadata and clinician warnings retained through the existing LangGraph pathway.
- Cloud transmission requires the explicit synthetic-only opt-in. The zip has no key or PHI from the source archive.

## Executed tests

- `python -m pytest -q tests/test_sarvam_batch.py tests/test_clinical_fidelity.py tests/test_multilingual_pipeline.py`
- **22 passed** (mocked cloud SDK + original multilingual/fidelity contracts).
- Broader available suite: **70 passed, 4 skipped**; skipped tests require missing Flask/LangGraph or other external components.
- Python compilation passed for modified application and core audio modules.

## Tests NOT executed / missing evidence

- Live API authentication, billable upload/poll/download against user's own Sarvam account.
- End-to-end Flask + real LangGraph runtime, due to missing Flask/LangGraph wheels and the isolated environment being unable to reach package indexes.
- Real synthetic `.ogg` sample recognition/accuracy, code-switching measurements, negative clinical terms, medical-grade evaluations.
- Real patient privacy processing/clinician acceptance. This is NOT production-ready and NOT approved for PHI.

## Next verification required on Windows

1. `python -m pip install -r requirements-dev.txt`
2. `python -m pytest -q tests/test_sarvam_batch.py`
3. `python scripts\validate_complete.py` (strictly checks graph + Flask)
4. `python scripts\sarvam_batch_smoke.py --file .\synthetic_tamil_english.ogg --confirm-synthetic --mode codemix --show-transcript`
5. `python scripts\run_demo.py`, upload synthetic `.ogg`, inspect draft/graph provenance and approve only after reviewing content.
