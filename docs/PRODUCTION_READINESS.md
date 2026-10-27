# Production readiness — explicit architectural boundaries

The supplied application intentionally only enables synthetic demo mode on localhost. A public Vercel foundation should not expose demo login or patient intake. This architecture is not approved to process clinical information.

Before allowing real records:

1. Implement a durable queue and worker for multi-minute voice jobs; the Flask request should return 202 with an idempotent job ID. Persist partial stages and deadline handling across restarts.
2. Migrate SQLite business tables and LangGraph SqliteSaver to independently administered PostgreSQL with migrations, connection pools, backup and tested restores.
3. Put audio, slide images and report documents into encrypted private object storage with tenant-scoped signed access; do not use Vercel Functions ephemeral disk.
4. Replace synthetic password accounts with appropriate authentication, MFA, hospital memberships, doctor onboarding, RBAC and document access audit.
5. Validate exact AWS model IDs, Converse compatibility, authorized API key/IAM credentials, geography/profile destination Regions, vendor data handling and cost limits.
6. Benchmark Tamil-English code-switched clinical audio and translation using clinician-reviewed datasets; measure transcription WER, field extraction correctness, unsupported findings, negation, laterality and measurement preservation.
7. Implement template standards, clinician-specific configuration, required-field rules, doctor approval semantics, versioned skill regression and safety sign-off.
8. Complete privacy impact assessment, data retention, incident response, security testing and relevant regulatory intended-use review.
9. Run full tests on the target cloud stack including cross-hospital isolation, upload/malware handling, graph recovery, queue replay, backup/restore and end-user accessibility.

All AI-generated findings must remain drafts until authorized clinician review. A graph checkpoint is not proof of clinical or security compliance.
