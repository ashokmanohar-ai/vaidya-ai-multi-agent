# AWS Bedrock configurable extraction — local synthetic demo

## What is real, and what is not

- **Real**: a model-agnostic `get_provider()` interface, an AWS Boto3 **Bedrock Converse** adapter, configurable AWS Region/model allowlist, runtime schema validation, model latency/token metrics, LangGraph Pathology Agent handoff, and no silent model fallback.
- **Not provided**: an AWS secret token, live Bedrock proof, medical transcription/translation, approval to process identifiable health data, or clinically validated medical extraction.
- The Learner graph is rule-based; `LLM_LEARNING_MODEL` is reserved for a future optional language-enhancement step and is **not** invoked today.

## Quick setup (Windows PowerShell)

Install packages using your existing Python 3.12 virtual environment:

```powershell
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, configure:

```dotenv
LLM_PROVIDER=bedrock
AWS_REGION=ap-south-1
AWS_DEFAULT_REGION=ap-south-1
AWS_BEARER_TOKEN_BEDROCK=<YOUR_REAL_TOKEN_HERE>
BEDROCK_MODELS=in.openai.gpt-5.6-terra,in.openai.gpt-5.6-luna
LLM_EXTRACTION_MODEL=in.openai.gpt-5.6-terra
ALLOW_REMOTE_SYNTHETIC_INPUT=true
BEDROCK_STRUCTURED_OUTPUT=false
```

**Never commit or share the `.env` file.** If the token is missing or blank, you can still run synthetic rule-based demo mode by setting `LLM_PROVIDER=demo`. The Bedrock adapter does not mock a successful live call.

### Verify model and connection first

```powershell
python scripts\preflight.py
python scripts\bedrock_smoke_test.py
# Previous command sends NO requests.
python scripts\bedrock_smoke_test.py --confirm-cost
# This explicitly makes ONE billable AWS Bedrock request, using synthetic text only.
```

If successful, start the synthetic leadership demo:

```powershell
$env:PORT='5055'
python scripts\run_demo.py
```

Visit http://127.0.0.1:5055. **Generate a new report** (seeded historical reports were rule-based fixtures). The new report should display provider `aws-bedrock`, your configured model ID, and node traces. In Admin → LLM provider configuration, inspect the recorded invocation latency and token usage when returned by AWS.

If the live Bedrock request fails, the report is **not silently switched to demo rules**. Switch `LLM_PROVIDER=demo` yourself to use the offline demo instead.

## Config controls

| Variable | Meaning |
| --- | --- |
| `LLM_PROVIDER` | `demo` or `bedrock` |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key; read automatically by a supported Boto3 SDK, never embedded in code |
| `AWS_REGION`, `AWS_DEFAULT_REGION` | Default `ap-south-1`; AWS SDK region |
| `BEDROCK_MODELS` | Comma-separated approved model ID allowlist |
| `LLM_EXTRACTION_MODEL` | Selected extraction model; must belong to configured allowlist |
| `ALLOW_REMOTE_SYNTHETIC_INPUT` | `true` is required to enable an external LLM call; synthetic cases only |
| `BEDROCK_STRUCTURED_OUTPUT` | Optional JSON Schema enforcement for supported models/profiles |
| `BEDROCK_MAX_OUTPUT_TOKENS` | 128–8192; default 1800 |
| `BEDROCK_TEMPERATURE` | Optional model-specific setting; leave unset if unsupported |

## Model selection caveats

The listed model IDs are candidate configuration values, **not verified entitlements**. Each Bedrock model and inference profile can differ in Region, required endpoint/API, JSON-schema support, `temperature`, and routing rules. AWS availability and per-profile data-processing destinations must be checked before use. The adapter currently uses **Converse** and does not automatically switch to Bedrock's OpenAI-compatible Responses API for models that do not support Converse.

The API key supports eligible Bedrock operations; it does not authorize arbitrary AWS service calls. Boto3's standard credentials provider chain also supports IAM/role-based AWS authentication when there is no bearer token. Avoid global inference profiles for patient information until governance approves routing.

## Clinical governance

No identifiable patient material in this package. Use synthetic samples only. Every LLM draft must be verified and approved by the authorized clinician, and any generated learning suggestions require separate authorized review. Neither the graph nor the model can approve reports or activate skills. Never include API keys, raw transcripts, or patient identifiers in logs/metrics.
