# AI providers

AI is optional. The Risk Manager always retains the governed/config-driven result separately from any AI-assisted result.

The project currently implements two provider types:

```text
azure_openai
openai_compatible
```

The generic OpenAI-compatible provider is intentionally conservative: it uses a single Chat Completions request for structured synthesis and does **not** assume that a non-Azure vendor implements OpenAI/Azure hosted web-search semantics.

## Capability matrix

| Provider/path | Current project support | Structured synthesis | Provider-hosted web search in Risk Manager | Notes |
| --- | --- | --- | --- | --- |
| Azure OpenAI | Native `azure_openai` | Yes | Yes, when available/permitted | Validated capability-driven Responses path. |
| OpenAI public API | `openai_compatible` | Yes when selected model/endpoint supports JSON-schema Chat Completions | No through generic adapter | Uses OpenAI-compatible Chat Completions; a dedicated native adapter could expose richer Responses tools later. |
| Google Gemini | `openai_compatible` via Google's official compatibility endpoint | Supported by Google's compatibility layer for compatible models | No through generic adapter | Google recommends native Gemini API for advanced tools such as grounding/search. |
| Claude | `openai_compatible` compatibility layer for evaluation | Not guaranteed for this workflow | No through generic adapter | Anthropic says `response_format` is ignored in its compatibility layer; use as evaluation only until a native Claude adapter is implemented. |
| vLLM / llama.cpp / Ollama-compatible gateway | `openai_compatible` | Depends on server/model | No | Useful for local/private inference; verify structured-output behavior. |

## Important: ChatGPT versus OpenAI API

ChatGPT is the interactive product. This application connects to the **OpenAI API**, not to a ChatGPT browser subscription/session.

For direct OpenAI use you need an OpenAI Platform API key and an API model available to your project.

## Install AI support

From `preservation_risk_manager`:

```powershell
python -m pip install -e ".[ai]"
```

For the full web/developer setup:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

## Configuration file

Keep local secrets in an uncommitted file such as:

```text
config/ai.local.json
```

Prefer environment variables for keys:

```json
{
  "ai": {
    "provider": "...",
    "endpoint": "...",
    "api_key_env": "MY_AI_API_KEY",
    "model": "..."
  }
}
```

Check configuration safely:

```powershell
python -m preservation_risk_manager.ai.cli info --config config\ai.local.json
```

The info command redacts inline API keys.

---

## 1. Azure OpenAI — native/validated path

Example:

```json
{
  "ai": {
    "provider": "azure_openai",
    "endpoint": "https://YOUR-RESOURCE.openai.azure.com/",
    "api_key_env": "AZURE_OPENAI_API_KEY",
    "api_version": "2024-10-21",
    "deployment": "YOUR_DEPLOYMENT_NAME",
    "temperature": 0.0,
    "max_output_tokens": 1200,
    "tokens_per_minute": 10000,
    "response_verbosity": "medium",
    "timeout_seconds": 60,
    "max_retries": 0,
    "external_research": {
      "allowed_domains": [],
      "blocked_domains": []
    }
  }
}
```

For capability-driven overall synthesis the provider makes a single Azure Responses call containing the complete assessment context. `web_search` is made available with automatic tool choice; the model decides whether to use it.

If institution-scoped/private assessment evidence is present, public web-search capability is suppressed for that call.

### TPM budgeting

`tokens_per_minute` is used to budget prompt plus structured-output reserve. It does not guarantee that Azure will never return a 429 because deployment usage can be shared/cumulative.

---

## 2. OpenAI public API

The project aliases `openai` to `openai_compatible`.

Example:

```json
{
  "ai": {
    "provider": "openai_compatible",
    "endpoint": "https://api.openai.com/v1",
    "api_key_env": "OPENAI_API_KEY",
    "model": "YOUR_OPENAI_CHAT_MODEL",
    "temperature": 0.0,
    "max_output_tokens": 1600,
    "timeout_seconds": 60
  }
}
```

The selected model must support the Chat Completions fields used by the project, including the structured-output schema required for synthesis.

The generic adapter does not expose OpenAI hosted web search. A future native OpenAI Responses adapter can add that without changing the higher-level Risk Manager contract.

OpenAI Platform API root/documentation:

```text
https://api.openai.com/v1
https://platform.openai.com/docs
```

---

## 3. Google Gemini through OpenAI compatibility

Google officially provides an OpenAI-compatible endpoint:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

Example:

```json
{
  "ai": {
    "provider": "openai_compatible",
    "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "api_key_env": "GEMINI_API_KEY",
    "model": "gemini-3.7-flash",
    "temperature": 0.0,
    "max_output_tokens": 1600,
    "timeout_seconds": 60
  }
}
```

Google's compatibility documentation includes Chat Completions and structured output. It also states that the compatibility path does not map every native Gemini feature and recommends the native Gemini API when advanced features such as provider-specific search/grounding are required.

In this project, therefore:

```text
Gemini via openai_compatible
  -> registry + methodology context
  -> one structured synthesis call
  -> no provider-hosted Google Search injected by the generic adapter
```

Official documentation:

```text
https://ai.google.dev/gemini-api/docs/openai
```

A future native Gemini adapter could expose Gemini-specific grounding/search while preserving the same Risk Manager authority boundary.

---

## 4. Claude through Anthropic's OpenAI compatibility layer

Anthropic provides an evaluation-oriented OpenAI SDK compatibility endpoint:

```text
https://api.anthropic.com/v1/
```

Example configuration for experimentation:

```json
{
  "ai": {
    "provider": "openai_compatible",
    "endpoint": "https://api.anthropic.com/v1/",
    "api_key_env": "ANTHROPIC_API_KEY",
    "model": "claude-sonnet-4-6",
    "temperature": 0.0,
    "max_output_tokens": 1600,
    "timeout_seconds": 60
  }
}
```

**Do not treat this as a production-validated Risk Manager provider yet.** Anthropic's compatibility documentation says the layer is primarily for testing/comparison and that `response_format` is ignored. This project relies on structured JSON output for reliable synthesis.

For production-grade Claude integration, implement a native Anthropic provider using Claude Structured Outputs and map its capabilities to the common `AIProvider` contract.

Official compatibility documentation:

```text
https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk
```

---

## 5. Local/OpenAI-compatible model server

Example:

```json
{
  "ai": {
    "provider": "local",
    "endpoint": "http://127.0.0.1:8000/v1",
    "model": "local-risk-model",
    "temperature": 0.0,
    "max_output_tokens": 1600,
    "timeout_seconds": 120
  }
}
```

`local` is an alias for `openai_compatible`.

Before operational use, verify that the server supports:

- Chat Completions;
- the JSON-schema `response_format` used by the project;
- required tool-call fields if using AI routing/helper workflows;
- the model's context window for the supplied evidence pack.

## Run the same assessment with any configured provider

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

The higher-level Risk Manager prompt/evidence contract remains the same across providers.

## Input logging

To capture the actual post-budget request sent to the provider:

```json
"input_log_file": "logs/ai-inputs.jsonl"
```

The log is append-only and includes messages, response schema and capability metadata. It excludes credentials but may contain internal/institutional evidence, so protect it accordingly.

## Domain filters

For providers where the application exposes external research capabilities:

```json
{
  "external_research": {
    "allowed_domains": ["loc.gov", "archives.gov"],
    "blocked_domains": []
  }
}
```

These are administrative restrictions, not evidence-ranking rules.

## Provider design rule

A provider adapter may change **how** a model is called; it must not change the governance boundary:

```text
registry/native evidence remains unchanged
configured governed synthesis remains visible
AI synthesis remains separate/advisory
external information is labelled separately
missing evidence remains missing
no automatic MongoDB write from AI output
```

## Adding a native provider

Implement the common `AIProvider` contract under:

```text
preservation_risk_manager/src/preservation_risk_manager/ai/providers/
```

Register it in:

```text
ai/factory.py
```

Advertise only capabilities actually supported by that adapter. Provider-specific web/search/grounding tools belong inside the provider boundary; the core synthesis code should not hard-code vendor APIs.

For implementation detail see [`../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md`](../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md).
