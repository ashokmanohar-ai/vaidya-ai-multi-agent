# VAIDYA AI Production Engineering Release — Validation Report

**Build date:** 17 October 2026
**Release classification:** production-engineering candidate **NOT production/clinical acceptance**

## Completed in the packaging environment

- Python compilation of the original code and new production modules: **passed**.
- Python automated tests: **60 passed, 4 skipped**. Existing legacy demo and newly written SQLAlchemy repository, S3 mock, auth/password, queue/retry, file gating and document-renderer tests included.
- JavaScript syntax check (`node --check production/static/console.js`): **passed**.
- Browser console (Chromium static render): **passed**; verified secure login screen layout. Static screenshots do **not** validate live Flask endpoints.
- ZIP integrity, mandatory source file checks and manifest SHA-256: performed at packaging time.

## Skipped / not demonstrated here

1. Flask application HTTP integration, including cookie/CSRF/UI navigation (Flask unavailable in this container; supplied tests run on operator machine).
2. LangGraph subgraph execution and human-interrupt resume using live `langgraph` packages (unavailable here).
3. Restart after checkpoint using an actual disposable PostgreSQL instance (none provisioned here).
4. Private S3 integration with real KMS key and IAM (only mocked S3 adapter tests run).
5. AWS Bedrock (no bearer token, account permissions, permitted profile or verified routing supplied); may be billable.
6. CPU faster-whisper model quality and medical Tamil-English accuracy, including negative clinical claims.
7. Load/concurrency, accessibility, security penetration tests, backup/restore and external clinical/regulatory reviews.

## What has changed

- Production API and console decoupled from the existing local synthetic demo.
- Durable database work queue with leasing/renewal and error handling; PostgreSQL schema and migration.
- PostgresSaver-backed LangGraph Orchestrator with Pathology/Learner subgraphs and human approval checkpoints.
- Private S3 artifacts with server-enforced hospital ownership, presigned uploads, bounded file types, and SSE-KMS.
- Stronger authentication, explicit account bootstrap, session/CSRF/role controls and SHA-256 report artifacts.
- Bedrock provider, optional approved compatible provider (no automatic fallback), optional local CPU ASR, independent translation and report-output warning checks.
- Clinician sign-off, deterministic signature-block learning candidate, admin approval and versioned skills.

## Production release decision

**BLOCKED pending external QA and governance evidence.** The software must not be presented as clinically safe or fully production-ready. Use the unchanged local leadership demo for synthetic presentations while executing the staging/prod runbook.

See `deployment/PRODUCTION_GATES.md` and `deployment/RELEASE_RUNBOOK.md`.
