# Preservation Risk Manager CLI reference

This document is the command-oriented reference for the current CLI surface.

For a first run across both packages, use [`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md) instead.

## Command routing

`python -m preservation_risk_manager` dispatches two integration commands specially:

```text
ask
query-json
```

All other commands use the deterministic/AI analysis CLI.

## `ask`

Human natural-language interface.

```powershell
python -m preservation_risk_manager ask `
  "What is the obsolescence risk of PDF?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Required:

```text
question
--framework
one of: --registry-json | --storage-config
--ai-config
```

Optional:

```text
--institution <id>
--limit <1..5000>
--json
```

Normal output is detailed human-readable text. `--json` returns canonical JSON plus router audit metadata.

## `query-json`

Machine/system interface. No AI routing.

Request file:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Literal request:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PDF","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Required:

```text
--framework
one of: --registry-json | --storage-config
one of: --request | --request-json
```

Output is always canonical JSON.

Current request actions:

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

Full request schema/examples: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md).

## `analyze-format`

Deterministic single-format analysis.

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

Required:

```text
--framework
one of: --registry-json | --storage-config
--format
```

Optional:

```text
--institution <id>
--readiness-status <value>
--exposure-level <value>
--include-unapproved
--evidence-summary
--compact-evidence
```

### Export mode handoff

When `--registry-json` points to `registry.json`, the file reader automatically loads a sibling:

```text
criterion_claims.jsonl
criterion_claims.json
```

if present. This is the normal handoff from registry-builder exports.

If neither exists and criterion claims are not embedded in `registry.json`, the analysis may correctly return `Not Assessed` because the framework has no normalized claims to consume.

## `analyze-format-ai`

Deterministic analysis plus bounded AI assistance/review.

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps
```

Additional required:

```text
--ai-config
```

Optional:

```text
--ai-mode fill-gaps|review-all
--max-ai-evidence-items <n>
```

Default AI mode is `fill-gaps`.

See [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md).

## `analyze-fixture`

Score explicit fixture evidence/answers without live registry access.

```powershell
python -m preservation_risk_manager analyze-fixture `
  --framework examples\qnl_sustainability.framework.example.json `
  --evidence-pack examples\pdf.evidence_pack.example.json `
  --answers examples\pdf.answers.example.json
```

Required:

```text
--framework
--evidence-pack
--answers
```

Useful for framework/scoring regression tests.

## `propose-policy-change`

Create an evidence-grounded draft proposal package for human review.

```powershell
python -m preservation_risk_manager propose-policy-change `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --institution qnl `
  --goal "Review whether the preservation action should change"
```

Required:

```text
--framework
one of: --registry-json | --storage-config
--format
--goal
```

Optional:

```text
--institution
--readiness-status
--exposure-level
--include-unapproved
--compact-evidence
```

This command does not automatically update policy.

## AI provider utility commands

Run through:

```text
python -m preservation_risk_manager.ai ...
```

Common commands:

### Show redacted config

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

### Provider smoke test

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation."
```

### Validate structured output

```powershell
python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json
```

### Validate tool calling

```powershell
python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

## Registry input modes

### `--storage-config`

Preferred for persistent integrations.

The risk manager reuses the registry-builder backend through `RegistryReader`.

### `--registry-json`

Preferred for export-only/offline interchange.

The file reader loads canonical formats from `registry.json` plus sibling criterion claims when available.

## Global and institution scope

### Global

No institution ID. Institution-scoped claims are excluded.

### Institution

For analysis commands:

```text
--institution qnl
```

For structured requests:

```json
{
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution scope includes global evidence plus claims belonging to that institution.

## Common result diagnostics

If a command succeeds but no band is returned, inspect:

```text
analysis_status
band_suppressed_reason
evidence_completeness
criterion_claims_used
missing_count
abstention_count
```

Suppression reasons are documented in [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md).

## Related docs

- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`FRAMEWORKS.md`](FRAMEWORKS.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
