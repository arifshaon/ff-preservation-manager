# AI provider interface

This is the **developer reference** for the provider-neutral AI layer in `preservation_risk_manager`.

For operator configuration, vendor examples, and the current Azure/OpenAI/Gemini/Claude compatibility matrix, use the canonical repository guide:

**[`../../docs/AI_PROVIDERS.md`](../../docs/AI_PROVIDERS.md)**

## Current implementation boundary

The application owns and preserves:

- resolved registry identity;
- source-native evidence and provenance;
- governed source-risk synthesis;
- criterion claims and framework configuration;
- deterministic question/gap/remediation results;
- registry writes and policy approval boundaries.

AI may be used for:

- natural-language request routing;
- bounded format-identification fallback;
- overall AI-assisted preservation-risk synthesis;
- `fill-gaps` question interpretation;
- `review-all` calibration/QA.

AI output does not silently rewrite MongoDB evidence, source-native assessments, reviewed mappings, or the governed/config baseline.

## Supported provider classes

### `azure_openai`

Implemented by:

```text
ai/providers/azure_openai.py
```

Azure supports the normal chat/structured-output path and, for eligible global overall synthesis, the Responses API with hosted `web_search` exposed using automatic tool choice.

### `openai_compatible`

Implemented by:

```text
ai/providers/openai_compatible.py
```

Aliases include:

```text
openai
local
openai-compatible
```

This path targets OpenAI-compatible hosted or local Chat Completions endpoints. It intentionally does **not** inherit Azure's hosted web-search behavior.

Compatibility depends on the endpoint/model actually implementing the OpenAI features required by the workflow, especially structured output and tool calling.

## Provider-neutral abstractions

Defined in `ai/base.py`:

```text
AIProvider
AIProviderCapabilities
AIRequest
AIResponse
AIUsage
AIMessage
AIToolDefinition
AIToolCall
AIError / AIConfigurationError / AIProviderError
```

Preservation logic should depend on these normalized types rather than vendor SDK response objects.

## Configuration

Loaded through `AIProviderConfig` in `ai/config.py`.

Important fields include:

```text
provider
endpoint
api_key / api_key_env
api_version
deployment / model
temperature
max_output_tokens
tokens_per_minute
response_verbosity
timeout_seconds
max_retries
human_format_assessment_limit
external_research.allowed_domains
external_research.blocked_domains
```

`web_research.enabled` may still be accepted from older local configuration for compatibility, but it is not the active capability switch. Capability availability is provider-driven.

## Secret handling

Prefer environment variables:

```json
{
  "ai": {
    "api_key_env": "QNL_AZURE_OPENAI_API_KEY"
  }
}
```

Do not commit real keys. Redacted configuration output must never reveal them.

## Diagnostic commands

Show redacted configuration:

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

Smoke test:

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation."
```

Validate structured output:

```powershell
python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json
```

Validate tool calling:

```powershell
python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

## Overall synthesis path

The active overall AI path is implemented primarily by:

```text
ai/capability_synthesis.py
ai/capability_result.py
```

The AI receives a compact, auditable context containing the resolved format, governed source assessments, source-native/criterion evidence, framework context, synthesis policy, and governed baseline.

For Azure global/public synthesis, a single Responses request may expose hosted web search. For OpenAI-compatible providers, the same high-level synthesis uses the provider's normal structured Chat Completions contract without Azure-specific web search.

Institution-scoped/private evidence suppresses public web-search capability while still allowing the configured model to analyse the supplied context.

The result records AI risk level, confidence, rationale, uncertainty, evidence references, capability use, and external URLs when returned. `capability_result.py` independently normalizes the reported relationship to the governed baseline from the returned semantic levels.

## Token budgeting

When `tokens_per_minute` is configured, structured synthesis reserves enough output room to finish valid JSON and compacts prompt evidence to remain inside the configured TPM allowance.

This budgeting is synthesis-specific; `max_output_tokens` remains the normal output setting for smaller routing/helper calls.

## Adding a provider

A new native provider should:

1. implement `AIProvider`;
2. accurately declare `AIProviderCapabilities`;
3. translate `AIRequest` to the provider API without changing preservation semantics;
4. normalize responses into `AIResponse`;
5. support structured output required by workflows that depend on it;
6. expose external/search capabilities only when genuinely supported;
7. preserve provider/model/usage/audit metadata;
8. add provider-contract tests;
9. register the provider in `ai/factory.py`.

Do not make source-risk logic, registry writes, or QNL policy provider-specific.

## Related documentation

- Operator/provider setup: [`../../docs/AI_PROVIDERS.md`](../../docs/AI_PROVIDERS.md)
- Installation: [`../../docs/INSTALLATION.md`](../../docs/INSTALLATION.md)
- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- AI analysis behavior: [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- CLI reference: [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- Human/system interface: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- Module reference: [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md)
