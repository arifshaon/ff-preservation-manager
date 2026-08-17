# AI provider interface

The preservation risk manager uses a provider-neutral AI interface so natural-language routing and bounded evidence interpretation are not coupled to one vendor/model.

The application—not the model—owns:

- registry evidence and provenance;
- format resolution;
- supported request actions;
- risk-framework questions/answers;
- deterministic answer derivation;
- scoring/banding;
- evidence-gap/remediation rules;
- institutional scope/posture;
- canonical JSON results;
- policy approval.

AI supplies language-model inference only within explicitly bounded workflows.

For the user-facing AI modes (`ask`, `fill-gaps`, `review-all`) see **[`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)**. This document focuses on the provider/configuration contract.

## Current providers

### Azure OpenAI

Use:

```json
"provider": "azure_openai"
```

Committed example:

```text
examples/ai.azure.example.json
```

Copy it to a local ignored config before inserting real credentials:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Example shape:

```json
{
  "ai": {
    "provider": "azure_openai",
    "endpoint": "https://example-resource.openai.azure.com/",
    "api_key_env": "QNL_AZURE_OPENAI_API_KEY",
    "api_version": "2024-10-21",
    "deployment": "<AZURE_OPENAI_DEPLOYMENT_NAME>",
    "temperature": 0.0,
    "max_output_tokens": 1200,
    "timeout_seconds": 60
  }
}
```

A direct local `api_key` is supported, but environment-variable/secret-store handling is preferred. Never commit real keys.

### OpenAI-compatible hosted/local endpoint

Use:

```json
"provider": "openai_compatible"
```

Aliases include `openai` and `local`.

A committed local template now ships at:

```text
examples/ai.local.example.json
```

Copy it:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.local.example.json config\ai.local.json
```

Template shape:

```json
{
  "ai": {
    "provider": "openai_compatible",
    "endpoint": "http://127.0.0.1:8000/v1",
    "model": "<LOCAL_MODEL_NAME>",
    "temperature": 0.0,
    "max_output_tokens": 1200,
    "timeout_seconds": 60
  }
}
```

Edit `endpoint` and `model` to match the local inference server. A key is optional for a compatible local endpoint that does not require authentication; the adapter supplies an internal non-secret placeholder to the SDK in that case.

This provider can be used with compatible vLLM, llama.cpp, Ollama gateways, or other OpenAI-compatible HTTP servers. Strict structured-output/tool support depends on the actual server and model, so validate capabilities before relying on human routing or AI-assisted analysis.

## Installation

AI SDK support is optional:

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
```

The `ai` extra installs the OpenAI Python SDK used by the Azure and OpenAI-compatible adapters.

Deterministic `query-json` and `analyze-format` do not require AI.

## Provider-neutral core abstractions

The `ai` package defines normalized application types including:

```text
AIProvider
AIProviderCapabilities
AIRequest
AIResponse
AIUsage
AIMessage
AIToolDefinition
AIToolCall
AIError / provider/configuration error types
```

Provider implementations translate these types to/from their SDK/protocol. Preservation logic must not depend on an Azure-specific response object.

## Configuration and secret handling

The loader can use a direct key:

```json
"api_key": "..."
```

or environment variable:

```json
"api_key_env": "QNL_AZURE_OPENAI_API_KEY"
```

Placeholder-looking configuration is rejected where required. Configuration description/redaction must never echo the secret.

## Validate configuration without a network call

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

This prints redacted provider configuration.

## Provider smoke test

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation that the provider is available."
```

This checks inference/connectivity only.

## Validate structured output

```powershell
python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json
```

Structured output is important because routing/evidence interpretation must return controlled application fields rather than free-form scores.

## Validate tool calling

```powershell
python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

Capability support should be verified independently for each local server/model combination.

## Current AI roles

### 1. Natural-language request routing

`ask` uses `ai/request_router.py`.

Example:

```text
Human:
"What are the software dependency risks of PDF?"

AI-routed request:
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  }
}
```

The router does not answer whether PDF is risky. It selects a supported action/parameters. `request_api.execute_request(...)` then queries the registry and runs deterministic assessment.

Machine integrations should bypass this AI step and send the structured request directly through `query-json` or a future wrapper around the same canonical request layer.

### 2. `fill-gaps` evidence interpretation

`analyze-format-ai --ai-mode fill-gaps` starts with deterministic answer derivation.

Only unresolved/ambiguous framework questions are eligible for AI interpretation. The model receives bounded evidence and must choose a framework-declared answer ID.

Safety properties:

- resolved deterministic answers are not replaced;
- fabricated evidence identifiers are rejected;
- model output cannot introduce arbitrary answer IDs;
- no usable evidence should result in abstention/no provider call rather than guessing;
- scoring remains deterministic after the controlled answer document is assembled.

### 3. `review-all` independent calibration

`analyze-format-ai --ai-mode review-all` independently evaluates eligible questions for calibration/evaluation.

The review prompt uses **raw-source-only evidence** and excludes deterministic answer/status, normalized mapped values used as answer shortcuts, score/band/posture, and mapping fields that would leak the reference answer.

After the model responds, its controlled answer is compared with the deterministic answer. A divergence is a review signal; it does not automatically change deterministic scoring or mappings.

## Example commands

### Human routing

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

### Fill unresolved questions

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps
```

### Independent review

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode review-all
```

## Structured output contract

`AIRequest` can carry a JSON Schema. Provider adapters normalize parsed output into `AIResponse.structured`.

Application code validates the result against its allowed action/answer schema before deterministic execution. A model's structured output remains untrusted input until validated.

## Tool calling contract

`AIRequest` can carry `AIToolDefinition` objects and providers can return normalized `AIToolCall` objects.

Future tool-oriented assistants should expose controlled application functions above `RegistryReader`/`request_api`, not arbitrary MongoDB access or scoring-rule mutation.

Appropriate boundaries include:

```text
resolve/search formats
execute canonical assessment request
get evidence/provenance
compare assessments/history
```

## Provider switching and deterministic equivalence

Switching providers/models must not change:

- stored evidence;
- identifier reconciliation;
- framework definitions;
- deterministic mapped answers;
- scoring code;
- band thresholds;
- evidence-gap/remediation rules.

Provider changes can affect routing quality or AI interpretation/review behavior, so those need evaluation, but the deterministic reference result remains application-owned.

## Evaluation areas

Useful AI evaluation dimensions include:

- format/request resolution;
- correct action selection;
- structured-output validity;
- appropriate abstention;
- evidence-reference validity;
- hallucination rate;
- agreement/divergence against reviewed deterministic examples;
- recommendation boundedness;
- latency/token usage.

## Related documentation

- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
