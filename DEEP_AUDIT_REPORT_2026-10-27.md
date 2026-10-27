# VAIDYA AI — Independent deep re-audit, 27 October 2026

**Scope:** The 18 October Sarvam V4 safety-updated ZIP was extracted and inspected, with a new set of defensive changes made after reproducing previously missed defects. This is a **localhost synthetic-data demonstration**, not a validated clinical system. Do not use identifiable patient data or release pathology reports on the strength of these tests.

## Reproducible checks

| Check | Result | Evidence / limitation |
|---|---|---|
| Original ZIP integrity and layout | PASS | ZIP CRC check succeeded; 109 project entries |
| Original regression suite | 80 PASSED, 4 SKIPPED | Fresh independent run (`python -m pytest -q`) |
| Repaired regression suite | 84 PASSED, 4 SKIPPED | Fresh independent run (`python -m pytest -q`) |
| Python compilation | PASS | `python -m compileall -q` for source/tests/scripts |
| HTML template parsing | PASS | 8 demo Jinja templates parsed |
| Browser JavaScript syntax | PASS | `node --check` for demo and production JS |
| DOCX generation | PASS | Fresh synthetic review DOCX generated and rendered; page visually inspected |
| Official Sarvam API lifecycle | DOCUMENTED, NOT LIVE-TESTED | Official docs confirm `create_job`, `upload_files`, `start`, `wait_until_complete(poll_interval, timeout)`, and `download_outputs`; SDK pinned to `0.1.36` |
| Docker image build | NOT VERIFIED | Docker daemon unavailable; Dockerfile was corrected and inspected statically |
| Windows 3.12/Flask/LangGraph integration | NOT VERIFIED | Framework packages unavailable in this container; 4 tests skipped |
| Actual Tamil–English audio transcription quality | NOT VERIFIED | No paid Sarvam call or identifiable source audio uploaded |
| Patient report clinical accuracy | NOT VERIFIED | Human reviewer + qualified evaluation required |

## High-priority confirmed defects and changes

1. **Contradictory atypical-cell text bypass (FIXED).** The final-document validator previously treated any occurrence of 'no atypical cells' as overriding a separate ambiguous occurrence of 'and atypical cells'. All ambiguous occurrences now block finalization, including when a separate negation is present elsewhere. Regression added.
2. **Unedited AI draft promoted to final (FIXED).** Final documents containing specific unverified section headers, unresolved placeholders or template warnings are now blocked from approval. Regression added.
3. **One-character approval (FIXED).** The synthetic demo approval endpoint now rejects final text shorter than 40 characters. This is only a basic anti-placeholder safeguard; length is not clinical validity. A Flask regression test is included but was not runnable in this environment.
4. **Concurrent final-file publication race (FIXED).** Previously, two approval requests could write the same final file before the database compare-and-swap update, allowing the losing request to overwrite the winning artifact. Reports are now rendered to random staging filenames, claimed inside a SQLite write transaction, and atomically published only by the winning request. Full concurrency stress testing still requires Flask integration.
5. **Docker image build would fail on missing dependency file (FIXED).** `requirements-production.txt` recursively references `requirements.txt`, but the original Dockerfile copied only the former before `pip install`. Dockerfile now copies both; `.dockerignore` added to exclude secrets, audio, uploaded data and large local environments. Actual build has not been run.
6. **Production Sarvam support previously ambiguous (CLARIFIED/FAIL-CLOSED).** Sarvam code is wired into the synthetic localhost app. The separate cloud production worker requires vetted local Faster-Whisper. When `ASR_PROVIDER=sarvam`, it now raises an explicit unsupported-provider error rather than failing misleadingly on missing `WHISPER_MODEL_PATH` or accidentally suggesting vendor approval. Clinical Sarvam processing is NOT enabled.

## Sarvam SDK contract cross-check

- Official documentation: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/batch-api
- Official job init: https://docs.sarvam.ai/api-reference/speech-to-text/stt/job/initiate
- Official keyterms: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/how-to/keyterms
- Current adapter selects `saaras:v4`, defaults to `codemix`, uses language auto-detection (`unknown`), supports `ta-IN` and `en-IN` overrides, validates a bounded keyterm list, and uses one sequential batch job per note to maintain note order.
- No fallback transcript is fabricated on network or model errors; requires explicit `ALLOW_REMOTE_SYNTHETIC_INPUT=true` for synthetic cloud data.
- SDK itself was not installed in the audit container, so compatibility remains a live-install verification requirement.

## Mandatory next checks on your Windows PC

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
python scripts\preflight.py
python scripts\validate_complete.py
python scripts\run_demo.py
```

Set private `.env` fields using `START_HERE_WINDOWS.txt`. Confirm a **synthetic** Tamil–English `.ogg` file, then run the documented billable Sarvam smoke test only after reviewing your privacy agreement and opt-in setting. Do not upload real patient recordings to this synthetic demo.

**Release decision:** Suitable for further local synthetic demonstration testing. **NOT CERTIFIED** for clinical use, live Sarvam success, Docker deployment, Windows compatibility, or end-to-end run until the outstanding gates pass.
