# Audio-first patient extraction — regression fix (27 October 2026)

## Original bug
`/reports/new` required `<select name="patient_id" required>` even in
`AUDIO_ONLY_MODE=true`. Flask rejected the submission unless a patient had
already been registered, and LangGraph required that record before calling ASR.
This contradicted the requirement to derive patient demographics from the audio.

## Corrected behaviour
- In audio-only mode, neither a patient dropdown nor synthetic-patient
  registration appears. The manual `/patients/create` endpoint returns 404.
- The audio-only POST rejects any submitted `patient_id` or typed transcript.
- Authorized uploaded audio is validated, submitted to the configured ASR,
  and must produce a nonempty transcript with provenance. **Only then** does
  `attach_audio_patient_candidate` extract literal name/age/sex and insert a
  per-job internal `AUDIO-<UUID>` record scoped to the doctor's hospital.
- Missing demographics remain empty/null, and malformed/failed ASR creates no
  placeholder transcript or identity. Orphaned candidates on failed reports
  are removed (when unreferenced).
- The generated draft is labelled **ASR; unverified**. In structured review,
  clinicians can verify/correct patient name/age/sex from the original audio.
  Any differing or missing ASR value requires an explanation in the audit log.
  Each of the eight pathology fields still requires individual verification.
- Prior legacy demonstration workflows remain separate and are not the
  recommended launcher for audio-based evaluation.

## Windows acceptance checklist
1. Extract the latest ZIP to a NEW folder, copy `.env.example` to `.env`,
   configure Sarvam API key, opt-in for approved de-identified evaluation data,
   and install dependencies.
2. Run `python scripts/run_real_audio.py` (not a previously running server).
3. Visit `/reports/new`: no synthetic Patient dropdown is present.
4. Upload a permitted OGG/WAV/MP3 file. If Sarvam fails, no draft appears.
5. If Sarvam succeeds, report shows audio-derived tentative demographics,
   original transcript, source hash metadata and a review form for corrections.
6. Correct discrepancies only from a verified recording; do not backfill from
   a target PDF merely to obtain a preferred output.
7. Run `python scripts/validate_complete.py` on a complete Windows install.

## Offline validation
`python -m pytest -q`: 110 passed, 4 skipped (this stage).
Tests include patient creation after nonempty ASR, missing demographics,
replay mismatch, clinician correction evidence and a rendered audio-only HTML
page without a patient dropdown or registry. Python compilation and test
DOCX generation passed. No live Sarvam API call, Flask/LangGraph Windows
execution, clinical accuracy validation, or medical clearance is claimed.
