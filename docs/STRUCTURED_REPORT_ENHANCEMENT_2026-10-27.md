# VAIDYA AI — Structured review and Sarvam V4 enhancement

**Date:** 27 October 2026  
**Scope:** localhost SYNTHETIC-development demo. Not a medical device; no real patient data permitted.

## What changed

1. **Synthetic patient creation.** On **Create report**, use **Create a matching synthetic patient**. Supply an invented `DEMO-*` reference, synthetic name, age and sex; the doctor role and CSRF token are required. Only the synthetic register is editable here; dictated speech does not silently overwrite patient identity.
2. **8-field structured review editor.** The **Review report** screen shows specimen, referring physicians, accession ID, received/reported dates, gross description, microscopy, and impression. Each field shows an **unverified** candidate (or stays empty). The reviewer edits the text and confirms each field individually after checking the original source.
3. **Strict validation.** Server-side review blocks empty fields, missing field confirmations, invalid/chronologically reversed dates, malformed accession identifiers, conflicting age/sex, conflicting patient names, unresolved placeholders, and ambiguous positive `and/or atypical cells` clauses. Audio-based reports additionally require five explicit source verification confirmations. Flags and transcription errors cannot be fixed by the LLM without review.
4. **Minor ASR spelling reconciliation.** A selected synthetic patient `Ananya` vs ASR `Anaya` may be reconciled **only** if the difference is one character, age/sex match, and the audio reviewer expressly checks the correction and supplies an explanation of at least 18 characters. Unrelated names, ages or sexes still block. The raw ASR is never changed. Note: this is a human assertion, not a clinical identity guarantee.
5. **Structured final DOCX.** The reviewed report has separate header/patient/referral/accession/dates and sections Gross, Microscopy, Impression, with a conspicuous demonstration-only notice. Field values and reviewer identity are stored in `jobs.review_json`; the previous draft and original transcript remain unchanged. The final DOCX is published using the existing exclusive SQLite status transition.
6. **Backwards-compatible migration.** `Database.init()` adds `review_json` to existing SQLite databases without deleting old jobs. Older unsafe audio reports cannot use the legacy free-text approval endpoint; they must pass the structured check. Typed-only legacy sign-off remains for older offline demos.
7. **Tests and sample.** `tests/test_structured_review.py` adds safety regressions. `scripts/validate_structured_review.py` creates `demo_outputs/VAIDYA_Synthetic_Structured_Verified_Example.docx` from fictional case data, with **no cloud calls**.

## Using the sample safely

1. Configure and launch the application as shown in `START_HERE_WINDOWS.txt`.
2. Login using the **synthetic demo** doctor account.
3. Click **Create report**. If your synthetic dictated patient is not already in the list, create them first using the **synthetic patient** form.
4. Choose the **matching synthetic patient**. Upload *approved synthetic* Tamil–English audio or enter synthetic text, and click **Generate draft**.
5. In **Review report**, inspect the original Sarvam output. Its strings are not verified facts; do not rely on the UI candidate dates if ASR has removed separators. Correct each field by listening to the original recording and checking independently verified synthetic source information. Verify the complete biopsy identifier and the actual spoken negation. A final Tamil instruction to add or amend a referring doctor must appear under referral, not Microscopy.
6. Check **Verified against original evidence** below **each of the 8 fields**, and all applicable audio review checkboxes, then attest and submit **Generate reviewed structured DOCX**.
7. Use **Download synthetic doctor final**. The preview initially shows the UNVERIFIED draft; the download contains the structured reviewed output.

**Expected behaviour on the previously supplied transcription errors:**

| Problem in unverified ASR | New review outcome |
|---|---|
| Selected Patient Alpha, dictated Ananya | **Blocked**; create/select a matching fictional patient and regenerate |
| `Anaya` vs linked `Ananya`, same age/sex | Blocked until one-letter correction is individually verified and reason recorded |
| `received 36` / `reported 47` | Date candidate **blank**; reviewer must enter two **verified** DD/MM/YYYY dates |
| Accession `2007` without prefix/year | Displayed only as ASR candidate; reviewer must enter confirmed complete identifier |
| `and atypical cells` | Must be corrected from the recording before finalization; output with the ambiguous phrase is rejected |
| Final Tamil instruction naming another doctor | Show original instruction for reviewer; doctor explicitly confirms referral field |

**Important:** These are blocking/review workflows; the application does **not** autonomously recover the reference PDF's exact spelling, ID, dates, or negation from mistranscribed audio. Accurate content requires an independently checked source and human review.

## Sarvam V4 + optional Bedrock

- `.env`: `ASR_PROVIDER=sarvam`, `SARVAM_MODE=codemix`, `SARVAM_LANGUAGE_CODE=unknown`, `SARVAM_API_KEY=<private>`, `ALLOW_REMOTE_SYNTHETIC_INPUT=true` **only for approved synthetic data**.
- Add optional recognition hints under `SARVAM_KEYTERMS` as a JSON array, max 50 unique strings of <=64 characters. Keyterms can influence recognition but cannot verify facts.
- Default `LLM_PROVIDER=demo` performs rule-based extraction. `LLM_PROVIDER=bedrock` enables the existing Bedrock adapter for approved synthetic text, subject to credential/model configuration; the output must still pass the same human review.
- `TRANSLATION_PROVIDER=passthrough` preserves original Tamil+English text; an optional Bedrock translation must be separately configured and verified.
- Localhost pilot uses synchronous Sarvam batch calls; long processing can block a web request. A background queue is needed before production deployment.

## How to validate on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
python -m pytest -q
python scripts\validate_structured_review.py
python scripts\preflight.py
python scripts\validate_complete.py
python scripts\run_demo.py
```

Open http://127.0.0.1:5055. For the historical files, keep your old `instance/` database for migration testing; use a separate, new data directory for a fresh demo.

## What remains unverified

- Live Sarvam SDK/network with your credentials and operating region.
- Real Windows Flask/LangGraph startup and full demo browser E2E; unavailable in packaging runtime.
- External PostgreSQL and production worker tests.
- Real Tamil–English clinical ASR accuracy, medical device validation, security/privacy audit, and clinical regulatory clearance.
- Production worker **still uses local Whisper**, not the Sarvam localhost provider. Do not deploy the demo routes for real clinical use.

Sample DOCX was generated, rendered and visually checked. This is an offline synthetic report layout check—not clinical verification.
