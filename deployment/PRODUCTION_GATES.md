# Production release blockers and clinical governance checklist

**This code is NOT a certified production clinical product.** All controls below need independent evidence. `VAIDYA_CLOUD_OPERATIONS_APPROVED` and `VAIDYA_CLINICAL_INPUTS_APPROVED` are technical gates, **not legal or clinical approvals**.

| Gate | Evidence needed | Included code | Status |
|---|---|---|---|
| Multi-agent orchestration | Live integration tests with real LangGraph and PostgresSaver | Graph definitions and integration test | Pending live test |
| Data isolation | Cross-hospital penetration tests, scoped DB/storage policies | Scoped repository and API checks | Partial |
| Identity assurance | Approved SSO/MFA, account lifecycle, session/security tests | Password login, lockout, CSRF | Partial |
| Private storage | Private S3, KMS, IAM, CORS security evaluation | Adapter + mock tests | Pending cloud test |
| Long-running processing | Real queues/workers, crash recovery, timeouts, backpressure | Postgres lease queue/heartbeat | Pending workload test |
| Clinical fidelity | Approved Tamil-English recordings, output/source exact-match, sign-off | ASR/translation/adapters, review | Not established |
| Bedrock inference | Enabled/approved model, region routing, Boto3 integration | Bedrock adapter | Pending live account test |
| Image fidelity | Malware scan, file parsing validation, contextual placement | Image format verification & deterministic renderer | Partial |
| Model governance | Model/prompt approval, no global routing of PHI, version pinning | Config/model gating, audit fields | Partial |
| Data protection | DPDP/privacy assessment, contracts, retention/deletion schedules | Fail-closed input flags | External approval needed |
| Regulatory intended use | Jurisdiction-specific device software determination | No autonomous diagnosis design | External review needed |
| Backups/recovery | Restore from point-in-time backup, S3 artifact recovery, checkpoint restore | Runbook only | Not tested |
| DevSecOps | CI, SAST/SCA, IaC scanning, secret scanning, DAST, pen test | Basic CI and tests | Partial |
| Observability | Error budgets, audit event export, cost dashboard, alerts | Operational metrics records | Partial |
| QA acceptance | Flask/API/E2E, accessibility, rate limits, concurrency, peak workload | Domain tests + optional integration | Incomplete |
| Clinical owner acceptance | Signed doctor workflow and approved template | Doctor attestation flow | External review needed |

**No clinical deployment or real patient-data demonstration until all required release gates are signed off.**
