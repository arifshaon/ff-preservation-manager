# AI Provider Interface

The preservation risk manager uses a provider-neutral AI interface so the preservation workflow is not coupled to one vendor or one model.

The application owns the preservation evidence, deterministic scoring, risk framework, tool definitions, and audit trail. AI providers supply language-model inference only.

## Current providers

### Azure OpenAI

Use `provider: "azure_openai"` for the QNL Azure OpenAI service.

The committed example is:

```text
examples/ai.azure.example.json
```

It contains the QNL endpoint and placeholders for the API key and Azure model deployment name.

Copy the example to a local configuration file before adding a real key, for example:

```powershell
mkdir config
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

`config/*.local.json` should remain local and must not be committed with a real API key.

Example configuration:

```json
{
  "ai": {
    "provider": "azure_openai",
    "endpoint": "https://qnl-openai-qadc-prod-001.openai.azure.com/",
    "api_key": "<QNL_AZURE_OPENAI_API_KEY>",
    "api_version": "2024-10-21",
    "deployment": "<AZURE_OPENAI_DEPLOYMENT_NAME>",
    "temperature": 0.0,
    "max_output_tokens": 1200,
    "timeout_seconds": 60
  }
}
```

The deployment name is required separately from the Azure endpoint.

### OpenAI-compatible hosted or local endpoint

Use `provider: "openai_compatible"` (aliases: `openai`, `local`) for an HTTP server that exposes an OpenAI-compatible chat-completions interface.

Example local configuration:

```json
{
  "ai": {
    "provider": "local",
    "endpoint": "http://127.0.0.1:8000/v1",
    "model": "<LOCAL_MODEL_NAME>",
    "temperature": 0.0,
    "timeout_seconds": 60
  }
}
```

Actual support for strict structured output and tool calling depends on the local inference server and model. The preservation application keeps the same `AIRequest` / `AIResponse` contract either way.

## Installation

The deterministic risk manager does not require an AI SDK. Install AI support explicitly:

```powershell
python -m pip install -e ".[dev,ai]"
```

The `ai` extra installs the OpenAI Python SDK used by the Azure and OpenAI-compatible adapters.

## Validate configuration without making a network call

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

This displays redacted configuration. It never prints the API key and does not contact the provider.

## Manual provider smoke test

After replacing the API-key and deployment placeholders:

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation that the preservation AI provider is available."
```

This is only a provider/interface smoke test. It is not yet a preservation-risk assessment.

## Structured output

`AIRequest` can carry a JSON Schema. The Azure provider sends it as strict structured output and parses the returned JSON object into `AIResponse.structured`.

This is the contract that will be used for preservation framework answers so the model returns controlled fields rather than free-form scores.

## Tool calling

`AIRequest` can also carry `AIToolDefinition` objects. Providers return normalized `AIToolCall` objects.

The next integration layer will expose preservation functions such as:

```text
resolve_format
assess_format
assess_formats
compare_formats
get_format_evidence
get_risk_history
get_preservation_actions
```

The AI assistant will decide which tool to call; the application will execute the tool and the deterministic preservation engine will remain authoritative for scoring.

## Intended analysis flow

```text
Registry evidence
    -> evidence pack
    -> deterministic answer derivation
    -> AI interpretation for unresolved/ambiguous questions
    -> validated controlled framework answers
    -> deterministic scoring
    -> risk band and local posture
    -> AI explanation / suggested action plan
```

The provider interface therefore does not contain preservation scoring rules. Switching from Azure OpenAI to another hosted model or to a local model must not change the deterministic scoring implementation.

## Secret handling

The loader supports either:

```json
"api_key": "..."
```

or an environment-variable reference:

```json
"api_key_env": "QNL_AZURE_OPENAI_API_KEY"
```

Direct keys are supported because local deployment may use configuration files, but real secrets should be kept in ignored local configuration or a secret store and never committed to GitHub.
