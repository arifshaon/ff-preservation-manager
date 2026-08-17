# Criterion mapping workflow

This layer lets registry-builder harmonise source-native observations into neutral `criterion_claims` without making institution-specific scoring decisions.

For the full source-onboarding path—from deciding the source boundary through adapter/transcription, criterion mapping, and risk-manager verification—start with:

[`../../docs/HOW_TO_ADD_A_SOURCE.md`](../../docs/HOW_TO_ADD_A_SOURCE.md)

Structured-source acquisition/adapter details:

[`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)

Narrative/PDF/unstructured-source transcription:

[`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md)

For a **simplified step-by-step mapping guide** covering new external sources, institution-level evidence, adding a genuinely new criterion, and AI-assisted DPC Bit List mapping, use:

[`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

Reusable DPC AI mapping prompt:

```text
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

For DPC or another narrative source, transcription and criterion mapping are two different reviewable artifacts:

```text
source PDF/HTML
 -> reviewed source-native transcription JSON
 -> adapter/audit
 -> criterion mapping draft
 -> human-approved mapping
 -> criterion_claims
```

Do not combine source transcription and criterion mapping in one opaque AI step.

Core rule:

```text
Criterion claims are observations.
Hazard bands are conclusions.
Actions are decisions.
Readiness is capability.
Framework binding is judgement.
```

The registry builder supports three criterion-mapping operating modes:

| Mode | Use when | Command |
|---|---|---|
| 1. Registry build only | Source ingest/reconciliation is needed but no criterion mapping is applied yet. | `python -m registry_builder run --config ...` with no enabled `criterion_mapping` block |
| 2. Mapping/backfill only | Source data already exists and mappings are added or corrected later. | `python -m registry_builder criterion-claims backfill --config ...` |
| 3. Integrated build + mapping | Normal production path once mappings exist. | `python -m registry_builder run --config ...` with `criterion_mapping.enabled=true` |

Mode 2 is an enrichment/repair path. Mode 3 is the efficient production path: mappings are applied in memory after `reconcile()` and before persistence, so the pipeline does not write records and then reread Mongo just to generate vocabulary claims.

## Mode 1 — registry build only

Use this when onboarding a new source before mappings exist or when the source is useful for identity/native hazard evidence independent of the neutral criteria layer.

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out out
```

This mode can produce useful canonical/source evidence, but it does not by itself guarantee framework-answerable `criterion_claims`.

For NARA or a NARA-like source, composite risk/rating fields may participate in separate hazard assessment, but those source conclusions must not be smuggled into primitive criterion claims.

## Mode 2 — existing data backfill

Do not wipe MongoDB to adopt this layer. Use the configured backfill path when mappings are added after source data already exists.

Dry run:

```powershell
python -m registry_builder criterion-claims backfill `
  --config config\criterion-claims-backfill.mongodb.example.json `
  --dry-run
```

Write claims:

```powershell
python -m registry_builder criterion-claims backfill `
  --config config\criterion-claims-backfill.mongodb.example.json
```

The same command supports explicit paths:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\criterion_claims_backfill.json
```

Backfill reads existing `canonical_formats` and `source_records`, writes `criterion_claims`, and does not reacquire NARA, PRONOM, LOC, DPC, or QNL source data.

## Mode 3 — integrated build with mapping

Use this once mappings are approved. Add this block to a pipeline config:

```json
"criterion_mapping": {
  "enabled": true,
  "mode": "apply",
  "criteria": "criteria/v1.json",
  "mappings": "criterion_mappings",
  "include_drafts": false,
  "scope": "all"
}
```

Then run the normal pipeline:

```powershell
python -m registry_builder run `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --workdir work `
  --out out
```

Internally the order is:

```text
acquire/extract -> normalize -> reconcile -> method profiles -> criterion mapping -> persist -> export
```

This means `criterion_claims` are generated from the active in-memory source records and reconciled canonical formats before persistence. Exports include `criterion_claims.json` and `criterion_claims.jsonl` when integrated mapping is enabled.

## Audit before mapping

Use the read-only audit before approving mappings, especially for new or narrative-transcribed sources:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\current_registry_evidence.json
```

The audit tells you what fields and values actually exist, and projects coverage when mappings are supplied.

For `standard_json` transcriptions, remember that full source records are retained under `raw`; source-native fields may therefore appear as paths such as:

```text
raw.native_fields.endangerment_category
```

A thin source-specific adapter can instead promote them to:

```text
native_fields.endangerment_category
```

Always map the field path actually emitted/stored; do not guess it from the publication.

## Validate mappings

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings
```

Validation rejects common leakage errors:

- risk level / numeric rating / hazard band -> primitive criterion claim;
- preservation action / preferred tools -> sustainability or technical criterion;
- URL presence -> `public_specification`;
- wildcard NARA rubric mappings;
- approved mappings without a human `decided_by`.

## New NARA-like or DPC-like sources

A preservation admin can add a new source in phases:

1. acquire or transcribe the source;
2. adapter emits source-native records, identifiers, and provenance;
3. inspect actual field paths with the audit;
4. mapping config translates approved source-native observations into criterion claims;
5. risk manager verifies the intended framework question can consume the claim.

A composite source risk score/category may still be retained as source-native hazard evidence even when it is not appropriate to map into primitive criteria.

Use this NARA-style template where appropriate:

```text
config/criterion_mappings/australian_nara_style.template.json
```

## AI-assisted mapping mode

AI does not approve mappings. It drafts a config for human review.

For generic sources, upload these files to the AI agent along with an audit JSON:

```text
config/prompts/propose_mapping/v1.0.md
config/prompts/propose_mapping/negative_rules.v1.json
config/criteria/v1.json
```

For the DPC Bit List, there are **two separate AI prompts**:

```text
# Stage 1: source transcription
config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md

# Stage 2: criterion mapping
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

Do not run Stage 2 against an unreviewed opaque PDF extraction and treat the result as production-ready. Preferred order:

```text
DPC PDF/HTML
 -> AI/manual transcription draft
 -> human-reviewed transcription JSON
 -> ingest/audit actual fields
 -> AI mapping draft
 -> human mapping review/approval
 -> criterion claims
```

For the mapping stage, supply where possible:

```text
reviewed DPC transcription/source export
config/criteria/v1.json
audit/source-field profile from the adapter
accepted mapping examples
config/prompts/propose_mapping/negative_rules.v1.json
```

The audit/field profile matters because the final `from_field` values must match the adapter's actual normalized output. An AI can understand the DPC document without that profile, but it must not pretend guessed field paths are production-ready.

The AI must return a JSON mapping draft. Save the draft outside `config/criterion_mappings/`, for example:

```text
drafts/dpc_bit_list.v1.proposal.json
```

Then validate it:

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\dpc_bit_list.v1.proposal.json
```

Only a human-reviewed mapping should be copied into `config/criterion_mappings/` with approved claim status, accepted rule status, and `decided_by` set.

Validation success confirms structural compatibility, not semantic correctness.

## Final consumer verification

After claims are written, verify through `preservation_risk_manager`.

For example:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format_questions","format":"PDF","filters":{"domains":["adoption_community_support"]},"scope":"global"}' `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

The intended source claim should be visible under the intended scope and framework question. If it is not, onboarding is incomplete even if the adapter and mapping validator both succeeded.

See [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) for institution-scoped examples and the workflow for adding a genuinely new neutral criterion.
