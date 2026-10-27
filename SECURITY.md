# Vaidya security architecture and reporting

Do not include patient identifiers, private reports, AWS bearer tokens, passwords or database URLs containing credentials in Git, issues, CI logs, screenshots or test datasets. Scope sensitive security bugs through a private channel to the repo owner.

Important fail-closed settings: `APP_ENV=production`, PostgreSQL `DATABASE_URL`, strong `FLASK_SECRET_KEY`, private S3+KMS, TLS-only origin allowlist, `VAIDYA_CLOUD_OPERATIONS_APPROVED`, and separately reviewed `VAIDYA_CLINICAL_INPUTS_APPROVED`. These flags are engineering protections, **not approvals**.

Documented outstanding security work: MFA/SSO, independent penetration test, centralized immutable audit sink, privacy retention lifecycle, managed backups, provider/region review, end-to-end release validation and operator incident response.
