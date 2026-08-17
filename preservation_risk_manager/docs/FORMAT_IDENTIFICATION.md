# Format identification and resolution

The preservation-risk workflow begins with a **format observation** that must resolve to one canonical format before risk analysis continues.

Typical inputs include:

```text
fmt/18
PRONOM fmt 18
application/pdf
.pdf
PDF 1.4
Adobe Flash SWF
```

The input may come from a human, an AIP metadata record, DROID, Siegfried, another characterization service, or an external integration.

## Core rule

```text
format observation
      ↓
programmatic resolution
      ↓ if unresolved/ambiguous and AI plugin enabled
bounded AI candidate selection
      ↓
verified local CanonicalFormat
      ↓
criterion evidence / risk analysis
```

Risk analysis does **not** begin until a canonical registry format has been resolved.

## Default mode: programmatic only

AI identification is disabled by default.

The resolver first uses the existing deterministic `FormatResolver` precedence:

```text
canonical ID                         highest
verified authority identifier
other authority identifier
exact name
MIME type
extension
alias                               lowest
```

Ambiguity is returned instead of guessed.

The identification layer then applies conservative syntax normalization before giving up. Current examples include:

```text
PRONOM fmt 18  -> fmt/18
fmt:18         -> fmt/18
fmt-18         -> fmt/18
x-fmt 123      -> x-fmt/123
```

This normalization changes syntax only. It does not use general format knowledge to infer a version or identifier.

## Optional AI fallback plugin

The AI plugin is implemented by:

```text
preservation_risk_manager.format_identification.AIFormatIdentificationPlugin
```

The orchestration layer is:

```text
IdentificationResolver
```

When enabled, AI is called only after exact/programmatic resolution remains unresolved or ambiguous.

### Safety boundary

The model receives a bounded shortlist of **existing local canonical registry candidates**.

It may:

- select one supplied candidate;
- provide a confidence value and rationale;
- abstain.

It may not:

- invent a PUID;
- invent a new canonical format;
- select a canonical ID that was not supplied;
- bypass the local registry;
- change preservation-risk evidence or scoring.

Even a high-confidence AI answer is accepted only if its selected `canonical_id` exists in the supplied local candidate set.

Default minimum accepted confidence is:

```text
0.80
```

## Failure behavior

AI is an optional enhancement, not a dependency of deterministic assessment.

If the provider:

- times out;
- is unavailable;
- returns malformed output;
- returns a candidate outside the supplied set;
- falls below the configured confidence threshold;
- abstains;

then the programmatic result is retained.

The response metadata reports whether AI was attempted and why it was accepted/rejected.

## Human mode

Human question routing already requires an AI provider. Format-identification AI remains separately opt-in.

Example:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of old adobe flash movie?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --enable-ai-identification
```

The same provider is reused for request routing and bounded identification fallback.

Optional threshold:

```powershell
--identification-ai-min-confidence 0.90
```

## Machine mode

Without AI:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PRONOM fmt 18","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

This uses programmatic normalization and resolution only.

With AI fallback enabled:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"old adobe flash movie","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --enable-ai-identification `
  --identification-ai-config config\ai.local.json
```

Optional threshold:

```powershell
--identification-ai-min-confidence 0.90
```

## Response metadata

Integration responses may include:

```json
{
  "identification": {
    "input": "PRONOM fmt 18",
    "normalized": "fmt/18",
    "method": "deterministic_normalization",
    "status": "resolved",
    "match_type": "verified_authority_identifier",
    "ai_attempted": false,
    "ai": {},
    "resolved_canonical_id": "...",
    "resolved_label": "PDF 1.4"
  }
}
```

AI-assisted example:

```json
{
  "identification": {
    "input": "old adobe flash movie",
    "method": "ai_fallback",
    "status": "resolved",
    "match_type": "ai_candidate_verified_local",
    "ai_attempted": true,
    "ai": {
      "status": "match",
      "confidence": 0.93,
      "accepted": true,
      "candidate_canonical_id": "..."
    }
  }
}
```

An AI provider failure leaves the deterministic result intact and reports a method similar to:

```text
ai_fallback_error_programmatic_result_retained
```

## Plugin contract

Additional identification mechanisms can implement the `FormatIdentificationPlugin` protocol:

```python
def resolve(
    query: str,
    *,
    candidates: list[dict],
    base_resolution: FormatResolution,
) -> tuple[dict | None, dict]:
    ...
```

This allows future plugins such as:

```text
DROID result parser
Siegfried result parser
PRONOM authority lookup
repository-specific identifier service
another AI provider/agent
```

The plugin returns a local candidate record plus audit metadata, or `None` to abstain.

## Future identification adapters

DROID/Siegfried ingestion is not yet implemented by this module. The intended boundary is:

```text
DROID / Siegfried / AIP metadata
        ↓
format observation / identifier
        ↓
IdentificationResolver
        ↓
CanonicalFormat
        ↓
existing risk workflow
```

Those future adapters should preserve identification provenance such as tool, tool version, method, and source/AIP record while keeping the downstream risk engine independent of the identification tool.

## Related documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md)
