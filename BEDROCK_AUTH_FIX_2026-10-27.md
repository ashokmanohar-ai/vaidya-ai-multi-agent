# VAIDYA AI — AWS Bedrock authentication fix (27 October 2026)

## Reported error

`IncompleteSignatureException` at `vaidya/providers.py: BedrockConverseProvider.extract` while invoking `Converse`, after Sarvam is configured and LangGraph reaches the extraction step. An `Authorization=...` fragment appeared in the AWS error. This is an **AWS credential/signing** failure. The log alone does not prove a successful audio transcript or medical extraction.

**Model configuration:** `in.openai.gpt-5.6-terra`, `ap-south-1` is the documented India geographic inference ID. This patch does not change the model.

## Fix and scope

* Added `BEDROCK_AUTH_MODE=profile|bearer|auto`, strict credential source separation, explicit AWS SSO profile sessions, and startup/preflight checks for conflicting credentials.
* Sanitizes Bedrock `IncompleteSignatureException`, expired credentials, permission and request-validation error messages, so the raw service error and its potential token fragment cannot be exposed by Flask.
* Reuses the existing `scripts/bedrock_smoke_test.py --confirm-cost` with safe feedback. The smoke test sends **fixed synthetic text** and incurs Bedrock token charges.
* Preserves Sarvam API key and authentication unchanged.
* Added offline contract regression tests. No live AWS or Sarvam API operations performed in this build environment.

## Windows clean setup using AWS SSO (recommended)

1. Extract the **new ZIP into its own folder**, not on top of an old build.
2. Install AWS CLI v2. In PowerShell, check `aws --version` and `aws configure list-profiles`.
3. Choose a profile already configured for your account. Example: `bedrock`.
4. Run `aws sso login --profile bedrock` and `aws sts get-caller-identity --profile bedrock`.
5. Copy `.env.example` to `.env`, set `BEDROCK_AUTH_MODE=profile` and `AWS_PROFILE=bedrock` (or your actual profile). Leave **no** `AWS_BEARER_TOKEN_BEDROCK` value. Keep `AWS_REGION=ap-south-1` and `LLM_EXTRACTION_MODEL=in.openai.gpt-5.6-terra`.
6. Remove conflicting credentials from the current PowerShell process if present:

```powershell
Remove-Item Env:AWS_BEARER_TOKEN_BEDROCK -ErrorAction SilentlyContinue
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
$env:AWS_PROFILE = 'bedrock'
```

**Important:** If a credential variable is set persistently at Windows User/System level, removing it for the current shell does not permanently remove it. Restarting the terminal may restore it. Never paste secret values into tickets, chats, shell history, or logs.

7. Create a fresh Python 3.12 environment inside the new project directory, install dependencies, preflight, then do the fixed synthetic Bedrock smoke test:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts\preflight.py
python scripts\bedrock_smoke_test.py --confirm-cost
python scripts\validate_complete.py
python scripts\run_real_audio.py
```

Only send an approved **synthetic / de-identified** audio recording through the localhost evaluation application. The Bedrock smoke test verifies extraction connectivity, not transcription quality.

## Alternative: Bedrock API key

Set `BEDROCK_AUTH_MODE=bearer` with a current *Bedrock* API key in `AWS_BEARER_TOKEN_BEDROCK` (not a Sarvam key). Remove `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and session token. Never prefix the key with `Bearer ` inside the environment variable. AWS manages that prefix in the SDK.

## If a different AWS error appears

* `IncompleteSignatureException`: wrong header/signing mode or credential interference. Check `BEDROCK_AUTH_MODE`, profile/token exclusivity, SDK versions, and proxy rewriting.
* `ExpiredTokenException` / invalid client token: refresh SSO or API key.
* `AccessDeniedException`: verify Bedrock model permissions, including `bedrock:InvokeModel` and inference profile access.
* `ValidationException`: check inference profile, region, Converse arguments and model access.
* Sarvam failure: a separate ASR stage, unaffected by this patch.

## Verification scope

Offline unit/integration mocks and source syntax are verified at packaging. **No claim** is made that the user's IAM account or region grants Bedrock access, that live Sarvam accurately transcribes pathology audio, that Windows execution works, or that clinical outputs are validated.
