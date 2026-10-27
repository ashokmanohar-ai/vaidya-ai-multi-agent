# VAIDYA AI — Technical MVP validation report

**Build date:** 17 October 2026  
**Artifact:** `VAIDYA_AI_Technical_MVP_Startup_Fix_20261017.zip`  
**Scope:** synthetic-only leadership prototype; **not clinically validated or production ready**.

## Validation executed in the packaging environment

| Validation | Result | Evidence / limits |
| --- | --- | --- |
| Domain and mocked Bedrock/translation tests | **PASS — 41 tests** | `python -m pytest -q` (includes callback registration regression test) |
| Flask/LangGraph integration suites | **NOT RUN — 2 skipped** | Python packaging environment cannot install Flask or LangGraph (offline package index). Test files are included for Windows. |
| Python source compilation | **PASS** | `python -m compileall -q app.py vaidya tests scripts` |
| Browser JS syntax | **PASS** | `node --check static/new_report.js` |
| Offline template renders | **PASS — 5/5** | Login, dashboard, new report, review and admin Jinja previews |
| Chromium visual screenshots | **PASS — 5/5** | `tests/capture_screenshots.py`, renders static previews rather than running Flask |
| DOCX formatting sample | **PASS, visual QA** | One-page approved-skill sample rendered and inspected; correct disclaimer, branding, image, signoff and no overflow |
| ZIP manifest / integrity | **Generated as final step** | Archive opened and checked with Python `zipfile.testzip()` |
| Actual speech recognition | **NOT VERIFIED** | Optional `faster-whisper` weights not available here; CPU transcription adapter covered by a fake ASR test |
| Live AWS Bedrock translation/extraction | **NOT VERIFIED** | No AWS bearer token provided; only mocked Converse calls tested |
| End-to-end browser ↔ Flask ↔ LangGraph ↔ SQLite | **NOT VERIFIED** | Requires dependencies and strict integration tests on target Windows installation |
| Cloud PostgreSQL, durable queue, patient-data security | **NOT IMPLEMENTED** | Out of local demo scope; must precede any real clinical deployment |
| Medical correctness / Tamil-English fidelity | **NOT VALIDATED** | Requires clinician-reviewed reference corpus and clinical signoff |

## Startup regression fix in this release

- Fixed the user-reported `UnboundLocalError: cannot access local variable 'await_doctor'` raised by `GraphRuntime.__init__` when starting `scripts/run_demo.py`.
- Moved both `await_doctor` and `verify_doctor_approval` definitions before Pathology graph node registration. Previously both were defined only **after** `pathology.add_node(...)` had already attempted to reference them.
- Added `tests/test_graph_initialization_regression.py`, which instantiates `GraphRuntime` using a stub LangGraph graph API and validates all three graph registrations, demonstrating the initialization ordering is valid without a live AWS model or Flask.
- Added the new regression test to `scripts/validate_complete.py` so it also runs in the Windows release gate.
- Rechecked Python compilation and all 41 available domain and stub-initialization tests.
- **Not verified here:** full LangGraph `SqliteSaver` execution, real `interrupt()`/`Command(resume=...)`, Flask HTTP routes, AWS Bedrock connection, or Whisper inference. These remain mandatory Windows/live integration checks.

## Technical changes in this update

- Multilingual intake supports up to five audio files, HTML microphone capture, and typed transcript plus audio.
- Added CPU Whisper provider, configured by `ASR_PROVIDER=faster-whisper`, model `WHISPER_MODEL_SIZE=tiny/base` or cached local directory.
- Added separately configured Bedrock translation provider, `TRANSLATION_PROVIDER=bedrock`, with source preservation and uncertainty flags.
- Original and translated transcripts persist separately; per-job `job_inputs` captures ordered audio and image references.
- Pathology LangGraph subgraph now includes ASR and translation nodes and provenance stages before extraction.
- Pydantic schema validation, numeric and laterality warning checks (not diagnostic verification).
- Active human-approved skills now feed Bedrock prompt and deterministic DOCX behavior. Each new job records skills version.
- Admin can rollback to an earlier skill content via an audited, newly appended immutable version.
- Updated reviewer/admin screens and sample reports, documentation and automation tests.

## Required Windows release gate

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts\preflight.py
python scripts\validate_complete.py
```

`validate_complete.py` must pass **without skipped tests**. It exercises real LangGraph checkpoint/interrupt/resume and Flask test-client interactions. A preflight dependency pass alone does not establish runtime functionality. Run a live UI test on `http://127.0.0.1:5055` and verify the checkpoint remains after server restart.

For optional CPU speech recognition:

```powershell
python -m pip install -r requirements-audio.txt
```

For live AWS, configure Bedrock region/model/access privately and explicitly opt in to **synthetic-only** requests, then run `python scripts\bedrock_smoke_test.py --confirm-cost`. Both translation and extraction can incur separate API charges. Never share tokens or use identifiable patient records.

## Honest release classification

This package is a **feature-expanded, synthetic technical MVP candidate**, not a fully implemented/clinically certified PRD solution. Open areas include specialty-specific templates, doctor-to-multiple-hospitals operations, fully contextual image placement, correction attribution to transcription/translation, extended regulatory/compliance work, real model and regional compatibility validation, durable cloud jobs, PostgreSQL checkpoints and encrypted production storage.
