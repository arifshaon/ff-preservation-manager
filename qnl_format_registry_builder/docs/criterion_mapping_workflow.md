# Criterion mapping workflow

This layer lets registry-builder harmonise source-native observations into neutral `criterion_claims` without making institution-specific scoring decisions.

Core rule:

```text
Criterion claims are observations.
Hazard bands are conclusions.
Actions are decisions.
Readiness is capability.
Framework binding is judgement.
```

The registry builder now supports three operating modes:

| Mode | Use when | Command |
|---|---|---|
| 1. Registry build only | Current behaviour; source ingest, reconciliation, hazard assessment, no criterion mapping | `python -m registry_builder run --config ...` with no `criterion_mapping` block |
| 2. Mapping/backfill only | Source data already exists and mappings are added or corrected later | `python -m registry_builder criterion-claims backfill --config ...` |
| 3. Integrated build + mapping | Normal production path once mappings exist | `python -m registry_builder run --config ...` with `criterion_mapping.enabled=true` |

Mode 2 is an enrichment/repair path. Mode 3 is the efficient production path: mappings are applied in memory after `reconcile()` and before persistence, so the pipeline does not write records and then reread Mongo just to generate vocabulary claims.

## Mode 1 — registry build only

This is the existing pipeline behaviour. Use it when onboarding a new source before mappings exist.

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out out
```

For NARA or a NARA-like source, this is already useful because source identifiers and composite risk/rating fields participate in reconciliation and hazard assessment. The source does not need criterion mappings to be useful as a hazard estimator.

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

The same command still supports explicit paths:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\criterion_claims_backfill.json
```

Backfill reads existing `canonical_formats` and `source_records`, writes `criterion_claims`, and does not reacquire NARA, PRONOM, LOC, or QNL source data.

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

Use the read-only audit before approving mappings, especially for NARA rubric questions and new NARA-like sources:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\current_registry_evidence.json
```

The audit tells you what fields and values actually exist, and projects coverage when mappings are supplied.

## Validate mappings

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings
```

Validation rejects common leakage errors:

- risk level / numeric rating / hazard band -> criterion claim
- preservation action / preferred tools -> sustainability or technical criterion
- URL presence -> `public_specification`
- wildcard NARA rubric mappings
- approved mappings without a human `decided_by`

## New NARA-like sources

A preservation admin can add an Australian/NARA-like source in two phases.

1. Adapter emits source-native records, identifiers, and any composite hazard estimator.
2. Mapping config translates approved source-native observations into criterion claims.

The composite source risk score is immediately useful as a hazard estimator even before criterion mapping exists. Mapping is enrichment, not a prerequisite.

Use this template:

```text
config/criterion_mappings/australian_nara_style.template.json
```

## AI-assisted mode

AI does not approve mappings. It drafts a config for human review.

Upload these files to the AI bot along with an audit JSON:

```text
config/prompts/propose_mapping/v1.0.md
config/prompts/propose_mapping/negative_rules.v1.json
config/criteria/v1.json
```

The AI must return a JSON mapping draft. Save the draft outside `config/criterion_mappings/`, for example:

```text
drafts/australian_preservation_framework.v1.proposal.json
```

Then validate it:

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\australian_preservation_framework.v1.proposal.json
```

Only a human-reviewed mapping should be copied into `config/criterion_mappings/` with `mapping_status: accepted` and `decided_by` set.
