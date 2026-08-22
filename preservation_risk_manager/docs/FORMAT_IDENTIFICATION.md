# Format identification and resolution

The preservation-risk workflow begins with a **format observation** that must resolve to one current canonical format before format-specific evidence can be assessed.

Typical inputs include:

```text
fmt/18
PRONOM fmt 18
application/pdf
.pdf
PDF 1.4
Adobe Flash SWF
```

The observation may come from a person, repository metadata, DROID, Siegfried, another characterization service, or an external integration.

## Resolution principle

```text
format observation
      ↓
programmatic normalization/resolution
      ↓ if unresolved or ambiguous and AI identification is enabled
bounded AI candidate selection
      ↓
verified local CanonicalFormat
      ↓
governed evidence/risk workflow
      ↓ optional
AI-assisted synthesis / question review
```

Risk analysis does not invent a new format identity. It operates on an existing local canonical registry record.

## Programmatic resolution

AI identification is disabled by default.

The resolver uses conservative precedence such as:

```text
canonical ID
verified authority identifier
other authority identifier
exact name/alias
MIME type
extension
```

Strong identifiers and exact identity signals outrank weak/generic matches. Ambiguity is returned rather than guessed.

Safe syntax normalization includes forms such as:

```text
PRONOM fmt 18  -> fmt/18
fmt:18         -> fmt/18
fmt-18         -> fmt/18
x-fmt 123      -> x-fmt/123
```

Syntax normalization does not infer an unknown version or identifier from general knowledge.

## Optional AI identification

Implemented through:

```text
IdentificationResolver
AIFormatIdentificationPlugin
```

When enabled, the model receives a bounded shortlist of **existing local canonical candidates** after normal programmatic resolution is unresolved or ambiguous.

The model may:

- select one supplied candidate;
- return confidence/rationale;
- abstain.

It may not:

- invent a PUID;
- invent a canonical format;
- select an ID outside the supplied candidate set;
- bypass the local registry;
- modify preservation evidence or risk results.

The default minimum accepted confidence is `0.80` unless overridden.

## Failure behavior

AI identification is optional. If the provider fails, times out, returns malformed data, selects an unknown candidate, falls below threshold, or abstains, the programmatic resolution state is retained.

This keeps format identification failure separate from preservation-risk evidence.

## Human use

Normal human query:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

Enable bounded AI identification only when useful:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of old adobe flash movie?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --enable-ai-identification `
  --identification-ai-min-confidence 0.85 `
  --ai-mode synthesize
```

AI identification and AI risk synthesis are separate stages. A specific PUID such as `fmt/276` normally does not need AI identification.

## Machine use

Prefer a request file in PowerShell:

```json
{
  "action": "assess_format",
  "format": "fmt/276",
  "scope": "global"
}
```

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

Optional AI identification flags:

```text
--enable-ai-identification
--identification-ai-config <path>
--identification-ai-min-confidence <0..1>
```

## Response audit metadata

Integration responses may include an `identification` object containing fields such as:

```text
input
normalized
method
status
match_type
resolved_canonical_id
resolved_label
ai_attempted
ai.accepted
ai.confidence
candidate_count
candidates
```

This lets consumers distinguish exact authority resolution, normalization, ambiguity, AI abstention, and accepted AI candidate selection.

## Plugin contract

Additional identification mechanisms can implement `FormatIdentificationPlugin` and return either a local canonical candidate plus audit metadata or `None` to abstain.

Potential future plugins include:

```text
DROID result parser
Siegfried result parser
repository-specific identifier service
authority lookup service
another bounded AI provider/agent
```

Identification provenance should be retained independently from the downstream risk result.

## Related documentation

- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- Operator use cases: [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md)
- Human/system requests: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- CLI reference: [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- AI provider implementation: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- Module reference: [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md)
