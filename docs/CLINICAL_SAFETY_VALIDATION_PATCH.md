# VAIDYA AI — clinical-content safety validation patch

**Date:** 18 October 2026  
**Product scope:** localhost, synthetic-data development demo only. **NOT FOR REAL PATIENTS OR CLINICAL DECISIONS.**

## What was fixed and why

Earlier sample reports could contain contradictory patient information: the Word header used the selected SQLite demo patient (for example Patient Alpha, age 45), while the raw ASR body described a different patient. A speech model also produced ambiguous “and atypical cells” wording; dates such as "36" and "47" were not reliably formatted; and a late referral-edit instruction appeared in clinical prose.

This patch:
1. Adds `vaidya/clinical_review.py` for **source-to-selected-patient comparison** and conservative section boundary identification, without rewriting the underlying ASR transcript. It flags patient name, age or sex conflict, malformed received/reported dates, number-only biopsy IDs, missing or altered negation, and possible post-impression referral edits.
2. Refuses approval when the selected patient and dictated identity disagree, even when attestation is provided. Such a job must be recreated using a correctly matched synthetic record; the app will not silently edit patient records.
3. Renders sections headed **Dictated context**, **Gross description**, **Microscopy** and **Impression**, whenever the transcript contains explicit headings. It keeps every section labelled **unverified**. A missing heading remains "Not clearly dictated", never inferred.
4. Treats possible Tamil/English referring-doctor edits as **instructions to verify** rather than clinical microscopic findings. Tamil words are preserved; there is no fabricated Tamil-to-English translation.
5. Requires an explicit audio-based verification checklist (audio listening, identity, numbers, negation and instructions) at sign-off. Simple checkbox attestation does not override hard mismatches or known ambiguous final text.
6. Adds a `validation_json` field to SQLite `jobs`, with safe additive migration. Older existing `draft_ready` jobs are reassessed automatically on review and approval so they cannot bypass the gate.
7. Adds offline regression tests in `tests/test_clinical_review_gate.py` and Flask+LangGraph integration tests in `tests/test_flask_e2e.py` (execute when the full dependencies are installed).

## Important known limitations

- The check is a **heuristic documentation safety screen**, not a diagnostic or medical-text entailment oracle. If the ASR itself missed a negation, software alone cannot reconstruct the spoken fact; verify against the recording.
- It does **not** force a transcript to match an uploaded reference PDF, and does not reconstruct `30/6` from `36`, `4/7` from `47`, or infer a full biopsy accession number from `2007`.
- The demo uses regex-based clinical section headings. If dictation is unclear or code-mixed, a doctor must edit the final text. `LLM_PROVIDER=bedrock` is optional, remote, non-deterministic and cannot replace source verification.
- A patient entry must already exist for the synthetic demonstration; a mismatch is intentionally blocked rather than resolved by guessing names. To demonstrate an audio case, use **fully synthetic matched** data. Do not import a real patient's identifiers into the demo dataset.
- Existing local `instance/` files and jobs are preserved but old drafts need fresh review; no previous report is automatically corrected.
- Sarvam has not been live-called by this packaging environment; no paid-provider, legal/consent, deployment, container or full Flask/LangGraph end-to-end assurance has been claimed.

## Windows quick start (new folder recommended)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
```

Set `DEMO_MODE=true`, `ASR_PROVIDER=sarvam`, `SARVAM_API_KEY=...`, `SARVAM_MODE=codemix`, `SARVAM_LANGUAGE_CODE=unknown`, and `ALLOW_REMOTE_SYNTHETIC_INPUT=true` **only for approved synthetic/de-identified recordings permitted by your provider agreements**.

```powershell
python scripts\preflight.py
python scripts\validate_complete.py
python scripts\run_demo.py
```

Open `http://127.0.0.1:5055`; if occupied, set `$env:PORT="8765"` before starting. Verify the ASR state on `/health/ready`. Use the tests and checklist before any leadership demonstration.

## Release gate

Use `python scripts/validate_complete.py` on the target Windows installation. It **requires** Flask, LangGraph and their real runtime tests; it fails if those integration tests skip. Here in the build container, 80 offline checks passed with 4 environment-dependent skips. The live paid Sarvam call and your Windows execution still require local validation.

## Data handling

Do not commit `.env`, API keys, existing patient documents, audio recordings, or `instance/`. The project ZIP intentionally excludes all of them. Your local `instance/` might still contain prior synthetic drafts; clear it intentionally only if you no longer need its data. Do not copy production patient data into this demo.
