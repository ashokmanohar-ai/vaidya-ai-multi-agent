# VAIDYA AI — real audio transcription integration

**Release candidate: 27 October 2026.** This replaces sample text as a transcription source in the **audio-only** workflow. The transcription is returned by Sarvam Saaras V4 on the **actual uploaded bytes**. It is not fabricated, seeded, or corrected using the expected report. **It is not guaranteed clinically accurate.**

## Scope and safety

This repository contains (1) a restricted Flask/LangGraph localhost evaluation app and (2) a separate, guarded API/worker architecture candidate. **Neither is approved for actual clinical use by merely setting an environment flag.** Do not send identifiable recordings to Sarvam or Bedrock until appropriate institutional authorization, informed consent/legal basis, vendor processing terms, applicable data residency/retention decisions and clinical assurance have been completed. The audio-only test launcher retains local demo credentials solely for testing and binds to `127.0.0.1`; do not expose it to the network.

The previously uploaded pathology PDF is a formatted final report, **not** a verified verbatim reference for measuring WER. A bilingual reviewer must create/verify a source-audio-aligned transcript. The system **must not** insert absent negations, add missing dates or override patient identity to imitate the expected PDF.

## Audio-only data flow

1. Doctor uploads the approved evaluation audio **without selecting or registering a patient**. The audio-only route rejects typed transcript submissions, preselected patient IDs and missing audio.
2. `vaidya.media.save_voice_notes()` validates the actual file signature and size and stores audio in the private test workspace.
3. `vaidya.multi_agent.GraphRuntime` validates secure private audio references. With `AUDIO_ONLY_MODE=true`, it never accepts/combines typed text.
4. `vaidya.audio.SarvamBatchTranscriber` opens the uploaded file and calls the real SDK: `create_job` → `upload_files` → `start` → `wait_until_complete` → `download_outputs`. One batch job per voice note preserves order. Non-completed jobs, malformed/ambiguous JSON and empty transcript results **raise** rather than fabricate content.
5. **Only after successful transcription**, the graph extracts a tentative patient name, age and sex from the ASR result and creates a per-job `AUDIO-<UUID>` internal candidate record. Any missing name/age/sex stays blank or null, without a fabricated patient identity. A clinician verifies/corrects these fields with an evidence note when changed.
10. The verbatim ASR result is preserved as `original_transcript` with detected languages, provider/model/mode, API job identifiers and SHA-256 hashes of uploaded bytes and transcript text. The original is never overwritten by optional translation.
10. Translation is a **separate** stage; `TRANSLATION_PROVIDER=passthrough` keeps the exact transcription text unchanged. `bedrock` performs real translation only if configured and authorized.
10. `LLM_PROVIDER=bedrock` invokes the existing Bedrock extraction agent. `LLM_PROVIDER=demo` uses limited deterministic **parsing of the real transcript**, not a fabricated transcription; it is inadequate for complex clinical extraction.
10. Existing identity/date/negation/section validators create **unverified** structured report candidates. A human must verify eight fields and each critical finding, including the presence or absence of atypical cells, before generating an approved evaluation document. Clinical release is separately gated.
10. On failure, no draft is created and uploaded local files from the failed attempt are cleaned up. The app never substitutes dummy text for failed ASR.

### Local Windows setup (approved evaluation audio only)

```powershell
cd C:\path\to\vaidya-ai-main
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`:

```dotenv
DEMO_MODE=true
AUDIO_ONLY_MODE=true
ASR_PROVIDER=sarvam
SARVAM_API_KEY=YOUR_PRIVATE_SARVAM_KEY
SARVAM_MODE=codemix
SARVAM_LANGUAGE_CODE=unknown
ALLOW_REMOTE_SYNTHETIC_INPUT=true
TRANSLATION_PROVIDER=passthrough
LLM_PROVIDER=bedrock
# Configure approved AWS credentials, AWS_REGION, model and permitted remote execution.
```

`ALLOW_REMOTE_SYNTHETIC_INPUT=true` is permission for **approved synthetic/de-identified evaluation material only**. Never mistake it for legal/clinical authorization for identifiable patients. Store credentials in `.env` or a proper secrets manager, not in scripts or the ZIP.

```powershell
python scripts\preflight.py
python scripts\validate_complete.py
python scripts\run_real_audio.py
```

Visit `http://127.0.0.1:5055`. Log in using the local evaluation credentials described in the README. **Do not select or create a patient.** Upload approved test audio in `.ogg`, `.wav`, `.mp3`, `.m4a` or `.webm` format (maximum 5 notes of 12 MB each). The new launcher uses a separate `instance_audio_only/` store and suppresses seeded patient examples, example reports and seeded learner examples. **The patient selector and registration panel are removed in audio-only mode.** Patient fields are created from actual ASR only and are explicitly unverified. You can correct name, age and sex against the original audio in the structured review form; corrections are audited and require a source-evidence note.

`LLM_PROVIDER=bedrock` requires a valid authorized AWS Bedrock configuration. If it fails, the report is **not generated**. The old demo-rules extractor remains in the repository for test compatibility and optional offline parsing, but it does not create substitute transcripts in audio-only mode.

### Direct paid Sarvam acceptance test

Use only an approved de-identified or fictional test recording. This sends audio to the Sarvam cloud and incurs charges.

```powershell
python scripts\transcribe_real_audio.py --audio "C:\approved\sample.ogg" --output "C:\private\asr_output" --confirm-approved-upload
```

Outputs (private, excluded from the release ZIP): `transcript.txt`, `asr_provenance.json`. No transcript is printed to the terminal. Review `transcript.txt` alongside the actual recording; the model can misrecognize names, dates and negations.

### Accuracy evaluation

Create a **manually verified verbatim** `reference.txt` from the same audio (including Tamil-English switching), then run:

```powershell
python scripts\evaluate_transcription.py --reference "C:\private\reference.txt" --candidate "C:\private\asr_output\transcript.txt" --critical-phrase "no atypical cells" --max-wer 0.10 --max-cer 0.10 --json-out "C:\private\metrics.json"
```

The tool reports word and character error rates, and absent critical phrases. It intentionally does **not** print private transcript text to stdout. Numbers, medication names, specimen IDs, dates, clinical negations and late Tamil editing instructions require a separate bilingual human review; WER/CER thresholds **do not** establish clinical safety.

## Guarded production API/worker

The production HTTP API requires `expect_uploads=true` and disallows client-supplied `transcript`; `Repository.submit_confirmed_uploads` requires at least one uploaded, confirmed **audio** object (images alone are insufficient). The production worker reads only actual audio objects from private S3; if absent/empty or a typed transcript is present it fails. If configured for Sarvam it requires **all** of `VAIDYA_CLINICAL_INPUTS_APPROVED`, `VAIDYA_CLOUD_OPERATIONS_APPROVED`, `VAIDYA_SARVAM_CLINICAL_APPROVED`, and `SARVAM_API_KEY` before external audio transfer. It stores `original.txt` and `asr_provenance.json` under the job's private prefix before translation/clinical extraction.

That is a code-level design—not clinical or infrastructure certification. A true production release still requires tested vendor agreements, S3 IAM/KMS isolation, PostgreSQL checkpoints, controlled retention/deletion, resilience, observability, AWS and Sarvam live checks, end-to-end container deployment and clinical risk management.

## Failure behavior

| Condition | Behavior |
| --- | --- |
| No uploaded audio / typed transcript in audio-only mode | HTTP 400; no graph transcription |
| Unsupported/corrupt audio container, oversized note | Validation error; not sent to provider |
| Sarvam key/SDK/opt-in missing | Not ready; no fake ASR fallback |
| Sarvam timeout, API/auth failure, failed job | Error propagated; no draft generated |
| Sarvam returns empty/missing or ambiguous JSON | Error; no invented transcript |
| Patient age/name conflict | Draft marked unverified; approval blocked |
| Malformed dates, missing biopsy prefix, unclear clinical negations | Human clarification required; never inferred from the final PDF |

## Reproducible validation status

See `REAL_AUDIO_VALIDATION_2026-10-27.md` for the exact checks performed and unverified live dependencies. 103 offline tests passed, four integration tests were skipped in the packaging environment because Flask/LangGraph/PostgreSQL are unavailable. The real Sarvam API was **not** invoked, and model word accuracy has **not** been established.

**Reference:** Official [Sarvam batch API](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/batch-api) and [keyterm limits](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/how-to/keyterms).
