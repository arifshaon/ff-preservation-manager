# Preservation Risk Manager CLI reference

This is the command-oriented reference for `preservation_risk_manager`.

For installation, start with [`../../docs/INSTALLATION.md`](../../docs/INSTALLATION.md). For copy/paste one-format and batch examples, use [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md).

## Entry point

```powershell
python -m preservation_risk_manager <command> ...
```

The two main integration commands are:

```text
ask
query-json
```

Other commands expose lower-level deterministic/AI analysis and utilities.

## `ask`

Human natural-language interface.

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

Required for normal human use:

```text
question
--framework
one of: --registry-json | --storage-config
--ai-config
```

Common optional flags:

```text
--ai-mode synthesize|fill-gaps|review-all
--institution <id>
--limit <n>
--json
--enable-ai-identification
--identification-ai-min-confidence <0..1>
--max-ai-evidence-items <n>
```

`ask` uses AI to interpret the human request. The application then resolves the format and executes the controlled registry/risk workflow. With `--ai-mode synthesize`, the final output also includes AI-assisted overall synthesis beside the governed/config baseline.

Use `--json` when you need the canonical machine payload and routing/AI audit metadata.

## `query-json`

Machine/system interface. The caller supplies the controlled action directly rather than asking AI to infer intent.

Request file:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

Literal request:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"fmt/276","scope":"global"}' `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

Required:

```text
--framework
one of: --registry-json | --storage-config
one of: --request | --request-json
```

Optional AI/identification flags include:

```text
--ai-config <path>
--ai-mode synthesize|fill-gaps|review-all
--enable-ai-identification
--identification-ai-config <path>
--identification-ai-min-confidence <0..1>
--max-ai-evidence-items <n>
```

When no AI mode is supplied, `query-json` executes the controlled application request without overall AI synthesis.

Current actions:

```text
assess_format
assess_format_questions
search_formats
assess_format_family
list_at_risk_formats
list_assessment_questions
list_evidence_gaps
plan_evidence_remediation
```

Request examples and response behavior: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md).

## `analyze-format`

Lower-level deterministic single-format framework analysis.

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --format fmt/276 `
  --evidence-summary
```

Required:

```text
--framework
one of: --registry-json | --storage-config
--format
```

Common optional flags:

```text
--institution <id>
--readiness-status <value>
--exposure-level <value>
--include-unapproved
--evidence-summary
--compact-evidence
```

This command is primarily for deterministic/framework diagnostics. The normal human overall-risk route is `ask`.

## `analyze-format-ai`

Question-level deterministic analysis plus bounded AI assistance/review.

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --format fmt/276 `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps
```

Supported modes:

```text
fill-gaps
review-all
```

Overall capability-driven synthesis is normally accessed through the integration commands with `--ai-mode synthesize`.

See [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md).

## `analyze-fixture`

Run framework/scoring tests from fixture files without live registry access.

```powershell
python -m preservation_risk_manager analyze-fixture `
  --framework examples\qnl_sustainability.framework.example.json `
  --evidence-pack examples\pdf.evidence_pack.example.json `
  --answers examples\pdf.answers.example.json
```

## `propose-policy-change`

Build an evidence-grounded proposal package for human review. It does not write policy automatically.

```powershell
python -m preservation_risk_manager propose-policy-change `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --format fmt/276 `
  --institution qnl `
  --goal "Review whether the preservation action should change"
```

## Web/API

Run the local UI/API:

```powershell
python -m preservation_risk_manager web `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --port 8080
```

Open:

```text
UI      http://127.0.0.1:8080/
Swagger http://127.0.0.1:8080/api/docs
OpenAPI http://127.0.0.1:8080/api/openapi.json
```

See [`../../docs/API_AND_SWAGGER.md`](../../docs/API_AND_SWAGGER.md).

## Batch/report command

The package exposes the `preservation-risk-batch` script for batch/report workflows. The preferred operator examples use the committed watchlist files and are documented in [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md).

## AI provider utilities

Run through:

```text
python -m preservation_risk_manager.ai ...
```

Show redacted config:

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

Provider setup: [`../../docs/AI_PROVIDERS.md`](../../docs/AI_PROVIDERS.md).

## Registry input modes

### `--storage-config`

Preferred for persistent operation. The Risk Manager reads the Registry Builder backend through `RegistryReader`.

### `--registry-json`

Portable/export mode. When the path is a Registry Builder `registry.json`, the reader also discovers sibling `criterion_claims.jsonl` or `criterion_claims.json` when present.

## Scope

Global:

```text
scope = global
```

Institution:

```text
--institution qnl
```

or in a structured request:

```json
{
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution scope adds matching institution-scoped evidence; it does not turn local observations into universal format facts.

## Common diagnostics

If framework/question analysis has no band, inspect:

```text
analysis_status
band_suppressed_reason
evidence_completeness
criterion_claims_used
missing_count
abstention_count
```

For identification issues inspect:

```text
identification.status
identification.method
identification.match_type
identification.ai_attempted
identification.ai.accepted
identification.ai.confidence
```

For overall synthesis inspect:

```text
governed_synthesis
overall_synthesized_risk
source assessments
capabilities_available
capabilities_used
external_sources
quality_warnings
uncertainty
```

## Related documentation

- Installation: [`../../docs/INSTALLATION.md`](../../docs/INSTALLATION.md)
- Operator use cases: [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md)
- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- Format identification: [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md)
- Human/system requests: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- AI analysis: [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- Frameworks: [`FRAMEWORKS.md`](FRAMEWORKS.md)
