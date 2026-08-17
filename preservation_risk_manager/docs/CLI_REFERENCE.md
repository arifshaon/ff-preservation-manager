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

The integration commands now pass format observations through `IdentificationResolver` before the canonical request executor. Programmatic identification is always available; bounded AI identification is opt-in.

See [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md).

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
--enable-ai-identification
--identification-ai-min-confidence <0..1>
```

Without `--enable-ai-identification`, format resolution remains deterministic/programmatic.

With it enabled, the same provider configured by `--ai-config` is reused as a bounded format-identification fallback after deterministic resolution/normalization fails or remains ambiguous.

Example:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of old adobe flash movie?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --enable-ai-identification `
  --identification-ai-min-confidence 0.85
```

Normal output is detailed human-readable text. `--json` returns canonical JSON plus router and identification audit metadata.

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

Optional identification flags:

```text
--enable-ai-identification
--identification-ai-config <path>
--identification-ai-min-confidence <0..1>
```

`--identification-ai-config` is required only when `--enable-ai-identification` is used in `query-json` mode.

Programmatic normalization example without AI:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PRONOM fmt 18","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

AI fallback example:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"old adobe flash movie","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --enable-ai-identification `
  --identification-ai-config config\ai.local.json
```

Output is always canonical JSON. When a request contains `format`, the response may include an `identification` section showing input, normalization method, whether AI was attempted, selected candidate, confidence, and acceptance/rejection metadata.

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

This lower-level command currently uses the deterministic `FormatResolver` directly. The optional identification plugin is exposed through the common human/system integration commands (`ask` and `query-json`).

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

This AI mode concerns **risk evidence interpretation/review**, not format identification. For AI-assisted format identification, use the integration commands and [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md).

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

## `build-training-corpus`

Build a versioned, leakage-gated fine-tuning corpus (Corpus A) from registry evidence.

```powershell
python -m preservation_risk_manager build-training-corpus `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --out corpus\ `
  --corpus-version 2026-09
```

Required:

```text
--framework
--registry-json | --storage-config
--out
--corpus-version
```

Optional:

```text
--tiers                            A,B,C (default A,B,C)
--abstention-share                 default 0.12
--abstention-tolerance             default 0.03
--split-seed                       default 20260901
--test-share                       default 0.15
--val-share                        default 0.10
--institution                      omit for a global corpus
--max-evidence-items               default 20
--min-test-examples-per-question   default 30
--max-answer-share                 default 0.90
--max-formats                      cap the scan for smoke runs
```

Writes `<out>/<corpus-version>/` containing `train.jsonl`, `val.jsonl`, `test.jsonl`,
`manifest.json`, and `leakage_report.json`.

Exits `2` with `status: quality_gates_failed` when a gate is violated. The corpus is still
written so the failure can be inspected.

See [`TRAINING_CORPUS.md`](TRAINING_CORPUS.md).

## `init-literature-inbox`

Create the drop folder for Corpus B, with a README explaining what to drop.

```powershell
python -m preservation_risk_manager init-literature-inbox --path literature\
```

## `build-literature-corpus`

Chunk and index PDFs/OCR text dropped in the inbox.

```powershell
python -m preservation_risk_manager build-literature-corpus `
  --inbox literature\inbox `
  --out corpus\ `
  --corpus-version 2026-09
```

Optional:

```text
--chunk-words          default 220
--chunk-overlap        default 40
--min-chars-per-doc    default 50 (PDF OCR check)
```

Writes `chunks.jsonl`, `index.json`, `manifest.json`, and `ingest_report.json`.
PDF input needs the optional `corpus` extra; `.txt`/`.md` needs nothing.

## `search-literature`

Search a built corpus and return citable chunk IDs with page numbers.

```powershell
python -m preservation_risk_manager search-literature `
  --corpus corpus\2026-09 `
  --query "JPEG 2000 renderer availability" `
  --limit 10
```

See [`LITERATURE_CORPUS.md`](LITERATURE_CORPUS.md).

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

For identification problems, inspect:

```text
identification.status
identification.method
identification.match_type
identification.ai_attempted
identification.ai.accepted
identification.ai.confidence
```

Suppression reasons are documented in [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md).

## Related docs

- [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`FRAMEWORKS.md`](FRAMEWORKS.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`TRAINING_CORPUS.md`](TRAINING_CORPUS.md)
- [`LITERATURE_CORPUS.md`](LITERATURE_CORPUS.md)
