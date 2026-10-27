# VAIDYA AI — Production Engineering Release Candidate (17 October 2026)

**Two separate applications live in this archive.**

1. `app.py` + `scripts/run_demo.py` — the familiar **synthetic-data leadership demo**, SQLite-based, no real patient data, runs locally on Windows at a configurable `PORT`.
2. `production_app.py` + `production.worker` — an **independent cloud-engineering candidate** built around Flask, LangGraph/PostgresSaver, SQLAlchemy/PostgreSQL, private S3, Bedrock, RBAC, durable work queue, doctor approval and governed learning. It is **not a certified clinical deployment**, and clinical inputs are disabled by default.

The complete original demonstration code remains intact, including the existing three LangGraph logical agents and local checkpointing. The hardened service does **not** silently fall back to demo models or clinical diagnosis.

## What is newly implemented

- Separate production configuration with enforced PostgreSQL, strong Flask signing secret, S3/KMS, HTTPS origin policy and two release gates.
- A fresh SQLAlchemy schema with Alembic baseline migration and operator-only bootstrap (no default passwords).
- Hospital-scoped doctor/patient/job repository, account lockout, SQL parameters, form-independent CSRF tokens, strict cookies and security headers.
- Durable work queue with atomic PostgreSQL claims, job idempotency, crash retry, leases/heartbeats and exhaustion recovery.
- Private S3 read/write, bounded presigned uploads, upload confirmation and content-type/size checks.
- One parent LangGraph Orchestrator with Pathology and Learner subgraphs; PostgreSQL checkpoints, doctor review interrupt/resume, administrator review interrupt/resume.
- Bedrock model-agnostic extraction adapter, optional Tamil/English CPU ASR using an explicitly preinstalled model, separate Bedrock translation node and deterministic DOCX rendering.
- Source and output references in S3, approved artifact checksums, skill versioning and evidence-based signature-pattern learning.
- A responsive HTML/CSS/JavaScript secure console, health endpoints, operator scripts, Dockerfiles, pytest regression suites and GitHub CI templates.

## How to run the unchanged synthetic leadership demo on Windows

Open PowerShell in this extracted folder and use an existing Python 3.12 virtual environment:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:PORT = "5055"
python scripts\validate_complete.py
python scripts\run_demo.py
```

Visit http://127.0.0.1:5055. There are **no real patient inputs** in this path.

## How to evaluate the hardened service with synthetic data

Review `deployment/RELEASE_RUNBOOK.md`, `deployment/ARCHITECTURE.md`, `deployment/PRODUCTION_GATES.md`.

```powershell
python -m pip install -r requirements-production.txt
python -m pip install pytest
python -m pytest -q production_tests tests
```

Production app boot requires approved infrastructure and fails closed without mandatory environment variables. **Do not set** `APP_ENV=production` / clinical input approval flags merely to bypass errors on a laptop. Configure a separate disposable Postgres staging environment and connect private staging S3 with fake patient data first. PostgreSQL/Bedrock integration tests require access to the actual resources and are not reproducible in a network-isolated packaging container.

## AWS Model Configuration

Set `AWS_REGION=ap-south-1`, `AWS_DEFAULT_REGION=ap-south-1`, `LLM_PROVIDER=bedrock`, `LLM_EXTRACTION_MODEL=<approved-profile>` and `LLM_TRANSLATION_MODEL=<approved-profile>`. The bearer token is read by Boto3 from `AWS_BEARER_TOKEN_BEDROCK` if available, but for hosted production prefer IAM roles and short-lived access. **Do not put actual tokens in GitHub or ZIP archives.** Global inference profiles are rejected for approved clinical data by this service.

## Production-readiness verdict

**Not yet authorized for medical production use.** Technical security and workflow controls are implemented, but live E2E testing on Flask/LangGraph/PostgreSQL/S3/Bedrock, penetration testing, clinical transcription/extraction validation, real patient-data retention controls, SSO/MFA, regulatory review, disaster recovery exercises, and clinician sign-off remain mandatory.
