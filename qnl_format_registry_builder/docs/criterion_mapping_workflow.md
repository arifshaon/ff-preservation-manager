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

## Existing data

Do not wipe MongoDB to adopt this layer. The first path is enrichment/backfill:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\current_registry_evidence.json
```

Then backfill approved mappings into the new collection:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out audit\criterion_claims_backfill.json
```

Use `--dry-run` first when reviewing a new mapping:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --dry-run
```

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
