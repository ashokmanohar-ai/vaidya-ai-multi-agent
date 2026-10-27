"""Explicitly authorized, potentially billable AWS Bedrock extraction smoke test.

Only fixed synthetic text is sent to AWS. Diagnostics never print secrets,
model-generated text, raw SDK exception messages, or input values.

Run from the Vaidya AI project root:
    python scripts/bedrock_smoke_test.py
    python scripts/bedrock_smoke_test.py --confirm-cost
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

# Environment variables already set in PowerShell take precedence over .env.
load_dotenv(ROOT / ".env", override=False)

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ParamValidationError,
    ReadTimeoutError,
    SSLError,
)
from pydantic import ValidationError as PydanticValidationError

from vaidya.providers import BedrockConverseProvider, bedrock_settings, bedrock_auth_configuration


SYNTHETIC_TEXT = (
    "Synthetic test only. Specimen: appendix. Dictated finding: acute appendicitis. "
    "Please bold acute appendicitis. The temperature was not provided."
)

# Only known schema fields are displayed. An unexpected key returned by a model
# is replaced with a label so it cannot leak content into diagnostic logs.
SAFE_SCHEMA_FIELDS = frozenset(
    {"findings", "instructions", "review_flags", "text", "instruction"}
)


def _safe_schema_location(location: object) -> str:
    """Render Pydantic error locations without echoing untrusted field names."""
    if not isinstance(location, (tuple, list)):
        return "<unknown-location>"
    parts = []
    for part in location:
        if isinstance(part, str):
            parts.append(part if part in SAFE_SCHEMA_FIELDS else "<unexpected-field>")
        elif isinstance(part, int) and not isinstance(part, bool):
            parts.append(f"[{part}]")
        else:
            parts.append("<unknown>")
    return ".".join(parts).replace(".[", "[") or "<root>"


def _safe_code(value: object) -> str:
    """Restrict externally supplied error codes to short, printable identifiers."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", value):
        return value
    return "<unavailable>"


def _diagnose(exc: Exception) -> None:
    """Report useful, sanitized diagnostics without exposing response content."""
    print(f"FAIL: {type(exc).__name__}")

    if isinstance(exc, PydanticValidationError):
        print("Stage: LOCAL PYDANTIC SCHEMA VALIDATION (AWS may have responded)")
        errors = exc.errors(
            include_input=False,
            include_context=False,
            include_url=False,
        )
        print(f"Schema errors: {len(errors)}")
        for error in errors[:15]:
            location = _safe_schema_location(error.get("loc", ()))
            error_type = _safe_code(error.get("type"))
            print(f"  - field={location} | type={error_type}")
        if len(errors) > 15:
            print(f"  ... and {len(errors) - 15} more (not displayed)")
        print("Next: check vaidya/schemas.py against the model's JSON contract.")
        print("If supported for this model, try BEDROCK_STRUCTURED_OUTPUT=true.")
        return

    if isinstance(exc, ClientError):
        # Do NOT print str(exc), the AWS Error.Message, or the request payload.
        response = exc.response if isinstance(exc.response, dict) else {}
        error = response.get("Error") or {}
        metadata = response.get("ResponseMetadata") or {}
        code = _safe_code(error.get("Code"))
        status = metadata.get("HTTPStatusCode")
        print("Stage: AWS BEDROCK SERVICE RESPONSE")
        print(f"AWS error code: {code}")
        if isinstance(status, int) and not isinstance(status, bool):
            print(f"HTTP status: {status}")
        if code == "ValidationException":
            print("Next: verify model ID, inference profile, Converse parameters,")
            print("and whether structured output is supported for this model/profile.")
        elif code in {"AccessDeniedException", "UnrecognizedClientException", "UnauthorizedException"}:
            print("Next: verify IAM permissions, token validity, and model access.")
        elif code in {"ThrottlingException", "ServiceQuotaExceededException"}:
            print("Next: check AWS service quotas and retry later.")
        else:
            print("Next: check Bedrock Runtime permissions, Region, and service availability.")
        return

    if isinstance(exc, ParamValidationError):
        print("Stage: LOCAL BOTOCORE REQUEST PARAMETER VALIDATION")
        print("Next: check installed boto3/botocore versions and outputConfig fields.")
        return

    if isinstance(exc, NoCredentialsError):
        print("Stage: AWS CREDENTIAL DISCOVERY")
        print("Next: configure a valid Bedrock API key or AWS profile/role.")
        return

    if isinstance(exc, (SSLError, EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)):
        print("Stage: NETWORK / TLS / TIMEOUT")
        print("Next: check proxy, TLS trust, DNS, network connectivity and Region.")
        return

    if isinstance(exc, RuntimeError):
        print("Stage: AUTHENTICATION / AWS BEDROCK RUNTIME")
        # The runtime error messages below come from approved hardcoded strings,
        # not AWS response messages. Keep this safe allowlist conservative.
        known_terms = {"IncompleteSignatureException", "expired", "access denied", "credentials", "model ID", "Authorization header"}
        if any(term.lower() in str(exc).lower() for term in known_terms):
            print("Next: check BEDROCK_AUTH_MODE, your AWS profile or Bedrock API key, and IAM permissions.")
        else:
            print("Next: review the local configuration and retry the synthetic smoke test.")
        return

    if isinstance(exc, ValueError):
        print("Stage: APPLICATION RESPONSE PARSING OR CONFIGURATION")
        # The following are hard-coded messages from the project's provider,
        # not dynamically sourced AWS/model text.
        known = {
            "Bedrock returned invalid JSON extraction": "Model returned malformed JSON.",
            "Bedrock returned missing/oversized extraction text": "No usable extraction text returned.",
            "Bedrock extraction must be an object": "Root value is not a JSON object.",
            "Bedrock response did not satisfy extraction contract": "Missing/non-list extraction arrays.",
            "Bedrock extraction exceeds safe item limits": "Extraction exceeded allowed item counts.",
            "Invalid finding item from Bedrock": "A finding has an invalid type or shape.",
            "Invalid instruction item from Bedrock": "An instruction has an invalid type or shape.",
            "Invalid review flag from Bedrock": "A review flag has an invalid type.",
            "Selected model is not in BEDROCK_MODELS allowlist": "Model is not on the local allowlist.",
            "Invalid Bedrock model ID": "Model ID failed the local format check.",
            "BEDROCK_MAX_OUTPUT_TOKENS must be between 128 and 8192": "Invalid maximum token setting.",
            "BEDROCK_TEMPERATURE outside 0–1": "Invalid temperature setting.",
        }
        detail = known.get(str(exc))
        if str(exc).startswith("Bedrock extraction failed JSON schema validation"):
            detail = "The model returned an incompatible JSON value; no report was generated."
        if detail:
            print(f"Reason: {detail}")
        print("Next: check the schema, structured-output mode, and .env values.")
        return

    if isinstance(exc, BotoCoreError):
        print("Stage: AWS SDK / CREDENTIAL PROVIDER")
        print("Next: check SDK version, credentials and the AWS network path.")
        return

    print("Stage: UNCLASSIFIED (details suppressed to protect data and credentials)")
    print("Next: inspect the exception locally in a secure development environment.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a potentially billable, synthetic-only Bedrock extraction request"
    )
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="Explicitly authorize a real AWS Bedrock inference request",
    )
    args = parser.parse_args()

    settings = bedrock_settings()
    print("VAIDYA AI - AWS BEDROCK SYNTHETIC SMOKE TEST")
    print(f"Region: {settings['region']} | Model: {settings['model']}")
    print(f"LLM provider configured: {settings['provider']}")
    print(f"Bearer token present: {settings['credential_configured']} (value never printed)")
    print(f"AWS_PROFILE present: {settings['aws_profile_configured']}")
    print(f"BEDROCK_AUTH_MODE: {settings['auth_mode']}")
    try:
        auth = bedrock_auth_configuration()
    except RuntimeError:
        print('FAIL: conflicting or missing AWS credential configuration (run scripts/preflight.py for details)')
        return 2
    print('Credential-source selection: ' + auth['mode'])
    print(f"Structured output requested: {settings['structured_output']}")
    print(f"Remote synthetic opt-in: {settings['remote_opt_in']}")

    if not args.confirm_cost:
        print("No request sent. Add --confirm-cost to authorize paid synthetic inference.")
        return 2

    if not settings["remote_opt_in"]:
        print("No request sent: set ALLOW_REMOTE_SYNTHETIC_INPUT=true in .env.")
        return 2

    if settings["allowed_models"] and settings["model"] not in settings["allowed_models"]:
        print("No request sent: LLM_EXTRACTION_MODEL is not listed in BEDROCK_MODELS.")
        return 2

    if not settings["credential_configured"] and not (
        settings['aws_profile_configured'] or settings['aws_static_keys_configured']
    ):
        print("Note: no explicit key/profile found in environment; the AWS SDK may use a default profile or role.")

    print("Sending fixed synthetic dictation only; AWS charges may apply.")
    try:
        result = BedrockConverseProvider().extract(SYNTHETIC_TEXT)
    except Exception as exc:
        _diagnose(exc)
        return 1

    print(f"PASS: real Bedrock extraction | {result.provider} | {result.model}")
    print(f"Latency: {result.latency_ms} ms | Token usage: {result.usage}")
    print(
        f"Synthetic findings: {len(result.findings)} | "
        f"format instructions: {len(result.instructions)} | "
        f"review flags: {len(result.review_flags)}"
    )
    print("Generated content requires doctor review. No actual patient data was sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
