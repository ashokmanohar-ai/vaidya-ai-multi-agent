# VAIDYA AI — Production Engineering Release Runbook

**Status: deployment candidate, NOT authorized for clinical production use.** Read `PRODUCTION_GATES.md` before operating on real patient data.

## Hosting architecture

- Private GitHub repository; production branch changes must be reviewed and tested.
- Vercel may host a **public informational frontend only** in the present configuration; use the Python Flask container as the authenticated clinical API. Its durable processing worker **must not** run in a Vercel request handler.
- Recommended production: separate web and worker containers on AWS ECS/Fargate, in an approved private network/VPC; AWS ALB/TLS/WAF; managed PostgreSQL (Amazon RDS), private S3 bucket with SSE-KMS, and Bedrock API/inference profile reviewed for data routing. No globally routed profiles for clinical inputs by default.
- Use an IAM task role scoped to S3, KMS and permitted Bedrock models, preferably no long-lived `AWS_BEARER_TOKEN_BEDROCK` for production.
- Persistent LangGraph checkpoints are stored in PostgreSQL via `PostgresSaver`. Graph is compiled per worker/API action and restores checkpoint using the stable `thread_id`.
- Clinical reports, source text, translations and images are in private S3, never Git or ordinary app logs.
- `production_app.py` and `production.worker` are separate entry points. The older `app.py` is a local, synthetic **leadership demo** and must not be used for clinical serving.

## Non-negotiable preflight

1. Complete the clinical intended-use/regulatory review and DPDP/privacy assessment for the jurisdiction; obtain a written pilot protocol from the hospital/practice.
2. Establish approved AWS region/profile routing for Bedrock, approved processor arrangements, data retention and deletion policy.
3. Deploy private S3 with encryption and restricted access; configure CORS only for approved browser origins and POST-only upload conditions.
4. Provision private PostgreSQL with encryption, automatic backups, PITR, restricted role permissions and tested restore. Operate HA/failover according to clinical RTO/RPO.
5. Create distinct application and migration DB roles. `init-db` and checkpoint setup are operator-only actions.
6. Provision SSO/MFA or equivalent approved identity system and validate the full tenant/doctor/patient threat model. The included password login is an engineering baseline, not a compliance certification.
7. Arrange security scanning, penetration testing, redacted tracing, clinician-labeled multilingual evaluation and downtime/failure exercises.
8. Configure verified account bootstrap without demo credentials.
9. Confirm approved error budgets, alerting, audit log access and immutable retention. Logs must never include PHI or bearer credentials.
10. Leave `VAIDYA_CLINICAL_INPUTS_APPROVED=false` until independent clinical/data protection owners authorize it.

## Local synthetic staging

In a temporary environment with explicit test flags only:

```bash
pip install -r requirements-production.txt
pip install pytest
python -m pytest -q production_tests tests
```

SQLite is allowed **only** for isolated repository and API tests. A real staging rehearsal must use a disposable PostgreSQL database, private object storage and the actual LangGraph checkpoint package. Set `VAIDYA_TEST_POSTGRES_URL` only for a disposable database, then run:

```bash
python -m pytest -q production_tests/test_postgres_checkpoints_optional.py
```

## Provisioning commands (only in authorized private infrastructure)

```bash
python -m production.commands init-db
python -m production.commands init-checkpoints
printf '%s\n' "$ADMIN_INITIAL_PASSWORD" | python -m production.commands bootstrap-admin --hospital 'Your Practice' --email 'admin@example.org' --name 'System Administrator' --password-stdin
printf '%s\n' "$DOCTOR_INITIAL_PASSWORD" | python -m production.commands create-user --admin-id '<admin-uuid>' --hospital-id '<hospital-uuid>' --email 'doctor@example.org' --name 'Approved Doctor' --role doctor --password-stdin
```

Do **not** copy secrets into shared shell histories or demo documents. Prefer secret-manager one-time bootstrap in a secure shell; these example commands illustrate stdin usage and are not a recommended live password delivery channel.

```bash
# Run separate services using Docker in approved infrastructure:
gunicorn -w 2 --threads 4 -b 0.0.0.0:8080 production_app:app
python -m production.worker
```

### Clinical API lifecycle

1. Doctor authenticates (`GET /api/v1/auth/csrf`, `POST /api/v1/auth/login`).
2. Register patient (`POST /api/v1/patients`).
3. Submit text plus patient reference and `Idempotency-Key` (`POST /api/v1/report-jobs`, returns queued job). For audio/image upload, use `expect_uploads=true` so the worker remains held.
4. Request presigned S3 POST (`POST /api/v1/report-jobs/{job_id}/uploads`); post to S3; confirm each (`POST /api/v1/report-jobs/{job_id}/uploads/{asset_id}/confirm`); finalize with `/uploads/complete`.
5. Worker runs Pathology graph and stops at doctor-review checkpoint. Poll job; download draft.
6. Authorized doctor uploads/approves final text via `/approve`. A durable `resume` task resumes the checkpoint, then the Learner graph analyzes differences.
7. Approved learning patterns are reviewed by an administrator and resumed via `/api/v1/admin/learnings/{id}/decision`.

### Migration and rollback

- `alembic upgrade head` must be preceded by a database backup and a dry run on a restored staging snapshot.
- **Never** run destructive downgrades over clinical records. The baseline migration intentionally forbids downgrade.
- For a code rollback, keep the database schema backward-compatible; restore a signed previous container image while preserving job/checkpoint IDs.
- Paused LangGraph nodes/state must remain compatible across versions; test resumed checkpoint migration on staging before release.

### Worker operations

- Worker leases are refreshed every 40 seconds during active processing. Maximum claims default to 3; exhausted leases become visible as failed.
- Monitor lease age, failures, retry delay, queue depth, generation latency, provider errors, storage failures, Bedrock costs and approval delays.
- Define alerting and protected incident runbooks for provider interruption, duplicate job attempts, unusual downloads and clinical-content discrepancies.

### Privacy/backup and recovery

- Define RPO/RTO with hospital; use continuous PITR where required, plus S3 versioning/object restore tests.
- Implement a legally approved data retention/deletion schedule including S3 versions, backups, model/provider logs and LangGraph checkpoints.
- Use privacy-preserving application metrics and an immutable audit event sink or protected database logging policy with minimum retention.
- A successful `health/live` only demonstrates web process liveness, NOT clinician-grade service availability.
