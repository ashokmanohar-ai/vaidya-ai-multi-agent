"""Fail-closed runtime configuration for the deployable clinical-service candidate.

No actual clinical use is authorized by this configuration alone; an external
clinical/privacy release decision and operator acceptance are also required.
"""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse
import os


def enabled(name: str) -> bool:
    return os.getenv(name, '').strip().lower() in ('1', 'true', 'yes')


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    aws_region: str
    s3_bucket: str
    s3_kms_key: str
    bedrock_model: str
    allowed_origins: tuple[str, ...]
    production: bool
    allow_clinical_inputs: bool
    sqlite_for_tests: bool
    s3_upload_origin: str = ""
    max_upload_bytes: int = 25 * 1024 * 1024

    @classmethod
    def load(cls) -> 'Settings':
        prod = os.getenv('APP_ENV') == 'production'
        sqlite_tests = enabled('VAIDYA_SQLITE_TEST_MODE') and not prod
        url = os.getenv('DATABASE_URL', '')
        if not url:
            raise RuntimeError('DATABASE_URL must be explicitly configured')
        if prod and not url.startswith(('postgresql://', 'postgresql+psycopg://')):
            raise RuntimeError('Production requires PostgreSQL, not SQLite')
        if not prod and not sqlite_tests and not url.startswith(('postgresql://','postgresql+psycopg://')):
            raise RuntimeError('Only explicit VAIDYA_SQLITE_TEST_MODE permits SQLite')
        if url.startswith('sqlite') and not sqlite_tests:
            raise RuntimeError('SQLite is restricted to isolated testing')
        secret = os.getenv('FLASK_SECRET_KEY', '')
        if len(secret) < 32 or secret.lower() in ('change-me', 'development-secret'):
            raise RuntimeError('FLASK_SECRET_KEY must be a strong secret of 32+ characters')
        region = os.getenv('AWS_REGION', 'ap-south-1')
        bucket = os.getenv('VAIDYA_S3_BUCKET','')
        kms_key = os.getenv('VAIDYA_S3_KMS_KEY','')
        if prod and not os.getenv('LLM_EXTRACTION_MODEL'):
            raise RuntimeError('A vetted LLM_EXTRACTION_MODEL is required in production')
        if prod and (not bucket or not kms_key):
            raise RuntimeError('VAIDYA_S3_BUCKET and VAIDYA_S3_KMS_KEY are required in production')
        if prod and not enabled('VAIDYA_CLOUD_OPERATIONS_APPROVED'):
            raise RuntimeError('Set VAIDYA_CLOUD_OPERATIONS_APPROVED only after deployment controls are reviewed')
        origins = tuple(x.strip().rstrip('/') for x in os.getenv('VAIDYA_ALLOWED_ORIGINS','').split(',') if x.strip())
        if prod and (not origins or any(not x.startswith('https://') for x in origins)):
            raise RuntimeError('Specify HTTPS-only VAIDYA_ALLOWED_ORIGINS in production')
        if prod and os.getenv('ASR_PROVIDER','sarvam').lower() == 'sarvam':
            if not enabled('VAIDYA_SARVAM_CLINICAL_APPROVED') or not os.getenv('SARVAM_API_KEY','').strip():
                raise RuntimeError('Production Sarvam requires explicit provider/data-governance approval and configured credentials')
        if prod and enabled('DEMO_MODE'):
            raise RuntimeError('Demo credentials must not be enabled in production')
        upload_origin=os.getenv('VAIDYA_S3_UPLOAD_ORIGIN','').strip().rstrip('/')
        if upload_origin and not upload_origin.startswith('https://'):
            raise RuntimeError('VAIDYA_S3_UPLOAD_ORIGIN must use HTTPS')
        return cls(url, secret, region, bucket, kms_key,
                   os.getenv('LLM_EXTRACTION_MODEL',''), origins, prod,
                   enabled('VAIDYA_CLINICAL_INPUTS_APPROVED'), sqlite_tests,upload_origin)

    def allow_real_input(self) -> None:
        if not self.allow_clinical_inputs:
            raise PermissionError('Clinical inputs disabled until explicit governance approval')
        if not self.production:
            raise PermissionError('Real clinical inputs not enabled in testing or local demo')
