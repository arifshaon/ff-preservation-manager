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
      ↓ if unresolved/ambiguous and AI identification enabled
bounded AI candidate selection
      ↓
verified local CanonicalFormat
      ↓
deterministic evidence / risk assessment
      ↓ if --ai-mode is enabled
bounded AI-assisted risk interpretation/review
```

Risk analysis does **not** begin until a canonical registry format has been resolved.

AI identification and AI risk assessment are separate permissions:

- `--enable-ai-identification` allows AI to help resolve an otherwise unresolved/ambiguous format observation against local registry candidates.
- `--ai-mode fill-gaps|review-all` enables AI-assisted risk analysis only after a canonical format has been resolved.

They may use the same configured provider, but enabling identification alone does not silently alter risk analysis.

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

Candidate generation for optional AI review is broader than deterministic identity resolution. Descriptive input is tokenized so exact observations such as `SWF`, `JPEG`, or `TIFF` remain strong shortlist signals even when embedded in longer prose.

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

If the identification provider:

- times out;
- is unavailable;
- returns malformed output;
- returns a candidate outside the supplied set;
- falls below the configured confidence threshold;
- abstains;

then the programmatic identification result is retained.

If AI risk assessment fails after canonical resolution, the deterministic risk assessment is retained and the response reports:

```text
error_deterministic_retained
```

The response metadata reports whether AI was attempted and why it was accepted/rejected.

## AI-assisted risk assessment after identification

Once identification succeeds, `--ai-mode` can continue the same request into the existing bounded AI risk engine.

### `fill-gaps`

```text
canonical format
   ↓
deterministic evidence pack
   ↓
deterministic answer derivation
   ↓
AI receives only unresolved/ambiguous questions + supplied evidence
   ↓
AI may interpret supplied evidence or abstain
   ↓
AI-assisted analysis + deterministic baseline retained
```

Deterministically resolved answers are not silently replaced in this mode.

### `review-all`

```text
canonical format
   ↓
deterministic baseline
   +
independent raw-source-only AI review
   ↓
agreement/divergence audit
```

This mode is for calibration and review. AI review does not replace deterministic scoring inputs.

## Human mode

Human question routing already requires an AI provider. Format-identification and risk-analysis AI remain separately controlled.

Identification only:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of old adobe flash movie?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --enable-ai-identification
```

Identification plus AI-assisted risk analysis:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of Adobe Shockwave Flash SWF?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --enable-ai-identification `
  --ai-mode fill-gaps
```

The same provider is reused for request routing, optional identification, and optional AI risk analysis.

Optional threshold:

```powershell
--identification-ai-min-confidence 0.90
```

## Machine mode

For Windows PowerShell, prefer a request file instead of inline JSON because native-command quote handling can alter embedded JSON quotes.

Create a request:

```powershell
$json = @'
{
  "action": "assess_format",
  "format": "Adobe Shockwave Flash SWF file",
  "scope": "global"
}
'@

[System.IO.File]::WriteAllText(
  "$PWD\request-flash.json",
  $json,
  (New-Object System.Text.UTF8Encoding($false))
)
```

Programmatic identification + deterministic risk assessment only:

```powershell
python -m preservation_risk_manager query-json `
  --request request-flash.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

AI identification fallback, but deterministic risk assessment:

```powershell
python -m preservation_risk_manager query-json `
  --request request-flash.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --enable-ai-identification `
  --ai-config config\ai.local.json
```

AI identification fallback **and** AI-assisted risk assessment:

```powershell
python -m preservation_risk_manager query-json `
  --request request-flash.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --enable-ai-identification `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps
```

For an already specific identifier such as `fmt/18`, AI identification is normally unnecessary; `--ai-mode fill-gaps` can still be used for the downstream risk stage.

`--identification-ai-config` remains accepted for backward compatibility and can supply the same provider when `--ai-config` is omitted in machine mode.

Optional controls:

```powershell
--identification-ai-min-confidence 0.90
--max-ai-evidence-items 20
--ai-mode review-all
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

AI identification output also includes the local shortlist audit (`candidate_count` and `candidates`) when AI is attempted, so an abstention can be distinguished from a genuinely empty local registry match.

When `--ai-mode` is enabled after successful identification, the response adds:

```json
{
  "ai_risk_assessment": {
    "status": "ok",
    "ai_mode": "fill-gaps",
    "provider": {},
    "criterion_claims_used": 0,
    "evidence_hash": "...",
    "deterministic_analysis": {},
    "analysis": {},
    "derived_answers": {}
  }
}
```

The normal deterministic request result remains present. This makes the AI layer additive and auditable rather than replacing the canonical deterministic response.

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
deterministic risk workflow
        ↓ optional
AI-assisted risk interpretation/review
```

Those future adapters should preserve identification provenance such as tool, tool version, method, and source/AIP record while keeping the downstream risk engine independent of the identification tool.

## Related documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md)
