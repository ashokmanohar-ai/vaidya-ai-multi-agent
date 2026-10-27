# VAIDYA AI — Sarvam Saaras V4 batch STT integration

**Status:** Implemented SDK adapter and offline mock contract tests. **No real Sarvam call or clinical validation performed in the packaging environment.** Only approved **synthetic or properly de-identified audio** may be submitted to this localhost demonstration.

## 1. Installation (Windows PowerShell)

```powershell
cd C:\path\to\vaidya-ai-main
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
```

Set the following **in your private `.env`**, never in the source tree or a public repository:

```dotenv
DEMO_MODE=true
ASR_PROVIDER=sarvam
SARVAM_API_KEY=YOUR_OWN_KEY
SARVAM_MODE=codemix
SARVAM_LANGUAGE_CODE=unknown
SARVAM_JOB_TIMEOUT_SECONDS=600
SARVAM_POLL_INTERVAL_SECONDS=5
ALLOW_REMOTE_SYNTHETIC_INPUT=true
TRANSLATION_PROVIDER=passthrough
LLM_PROVIDER=demo
```

`SARVAM_LANGUAGE_CODE=unknown` auto-detects. Test with `ta-IN` if it loses the Tamil instruction; compare with `en-IN` for English-majority recordings. **Forcing a language can worsen recognition of the other language.** `SARVAM_MODE=codemix` keeps English in Latin script and Tamil in Tamil script where recognised. `mode=transcribe` is another baseline; `mode=verbatim` is useful for numeric accuracy checks. `SARVAM_KEYTERMS` may be a JSON string array of up to 50 distinct terms, each 1–64 characters. Defaults are generic pathology terms; do not use terms to invent medical findings.

## 2. Runtime workflow

`Flask form → validated private audio storage → Pathology LangGraph transcribe node → Sarvam SDK batch create_job → upload_files → start → wait_until_complete → download_outputs → UTF-8 JSON parse → original transcript → Bedrock or passthrough translation → extraction → conservative validation warnings → clinician-approved DOCX draft`.

- All supported 32-second WhatsApp OGG recordings use **batch**, avoiding Sarvam's 30-second REST limit.
- For 1–5 notes, this local pilot uses **one Sarvam batch job per note** to preserve order safely and avoid mismapping output JSON filenames. The SDK supports bigger grouped jobs; use one grouped job with stable input-output mapping and async workers for cloud deployment.
- The provider transmits audio to Sarvam and can incur charges. The server refuses cloud transcription unless `ALLOW_REMOTE_SYNTHETIC_INPUT=true` is set.
- Each job is polled with bounded interval/timeout, must report a completed state, and must yield one valid downloaded transcript. No mock, silent fallback, or fabricated text on errors.
- The temporary Sarvam JSON output directory is removed automatically. Original uploaded audio resides in the local private `instance/audio` directory; delete it under an approved retention policy.
- The original code-mixed transcript is retained alongside optional English translation. `TRANSLATION_PROVIDER=passthrough` performs **no translation**. When using `TRANSLATION_PROVIDER=bedrock`, translation requires separate Bedrock credentials and approval.
- Review page displays ASR provider, mode and detected language from `job_inputs` metadata, plus a medical accuracy caution. Internal job IDs are retained for audit metadata without patient content.
- Report approval remains explicitly human. No machine confidence or keyword is evidence of clinical accuracy.

## 3. Validating offline and in your approved cloud account

```powershell
python -m pytest -v tests\test_sarvam_batch.py
python scripts\validate_complete.py
python scripts\preflight.py
python scripts\run_demo.py
```

Open http://127.0.0.1:5055, sign in as the synthetic demo doctor, and upload **synthetic** `.ogg` notes. The Flask request blocks while Sarvam runs; for production use a worker queue, progress states, retries with idempotency, and scheduled cleanup.

To test the adapter alone with **synthetic** audio (explicitly billable):

```powershell
python scripts\sarvam_batch_smoke.py --file .\synthetic_tamil_english.ogg --confirm-synthetic --mode codemix --language-code unknown --show-transcript
```

If the mixed-language result is poor, repeat with `--language-code ta-IN` and optionally `--mode transcribe` or `verbatim`, and compare exact negations/dates/medical terms manually. Each run may be billed.

## 4. Clinical privacy and production limitations

This repository remains a localhost-only synthetic demonstration: **not a real-patient production application**. Confirm consent/legal basis, data processing agreements, overseas transfers, residency, retention and security of the Sarvam provider **before any identifiable UK health information is transmitted**. Sarvam may use cloud storage/services outside your AWS account; using AWS Bedrock downstream does not change this.

Production readiness additionally requires a durable background queue, encrypted object storage, tenant and role isolation, removal/retention policy, end-to-end audit, rate limiting, provider failure recovery, independent clinical gold-set evaluation and clinician sign-off. The source transcript is an ASR hypothesis, not a verified clinical record. In particular, **"no atypical cells" vs "atypical cells" is safety-critical**.

## 5. Technical references

- SDK Batch API: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/batch-api
- Initiate: https://docs.sarvam.ai/api-reference/speech-to-text/stt/job/initiate
- Keyterm prompting: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/how-to/keyterms
- Source run against official Python SDK interface: `sarvamai==0.1.36`.
