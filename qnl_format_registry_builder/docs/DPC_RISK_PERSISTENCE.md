# DPC mapped risk-assessment persistence

## Purpose

DPC Bit List source records remain immutable, source-native `evidence_only` records. They do not create or merge canonical format identities.

Reviewed DPC-to-format mappings are persisted separately as versioned `risk_assessment_claims`. The current canonical `risk_assessments` and `synthesized_risk` fields are a materialized query view derived from those claims plus the registry's other risk evidence.

## Production config

```text
config/dpc_risk_assessment_backfill.production.json
```

The production config uses:

```text
config/external_risk_mappings/dpc_bit_list_2025.v1.approved.json
```

and enables source-level replacement:

```text
replace_source_claims = true
materialize_canonical = true
```

## Claim identity and history

A DPC mapped claim is keyed by:

```text
canonical_id
source_id
source_record_id
mapping_rule_id
mapping_version
```

A new mapping version therefore produces a new claim identity. Current claims from the same DPC source that are no longer produced are retained with:

```text
current = false
superseded_by_run_id
superseded_at
superseded_reason = source_replaced_by_risk_backfill
```

Re-running the same mapping version is idempotent: the same logical claim is refreshed rather than duplicated.

## Canonical materialization

Only mapped DPC assertions are replaced. Before materialization, the backfill rebuilds the normalized baseline from:

```text
risk_assessments
external_hazard
institution_policy_overlays
source_records
```

This preserves legacy NARA risk evidence and institutional/QNL overlays while allowing DPC assertions to be replaced independently.

The current synthesis method is scope-aware:

```text
exact_format / format_version
format_family
format_group
content_type
contextual
```

The most-specific available tier determines the headline semantic risk. Broader assessments remain available as contextual contributors and cannot override a more-specific assessment.

## Review workflow

Always run the dry run first:

```powershell
python -m registry_builder.dpc_risk_assessment_backfill `
  --config config/dpc_risk_assessment_backfill.production.json `
  --dry-run `
  --out out/dpc-risk-backfill-dry-run.json
```

The dry run performs no writes. Review at least:

```text
claims_generated
current_claims_before
claims_to_supersede
canonical_records_to_update
mapping_report.rules_applied
mapping_report.rules_skipped
mapping_report.assessments_attached
sample_changes
```

For the approved DPC 2025 mapping v1 against the current QNL registry baseline, the reviewed PDF mapping is expected to generate 51 format-group claims, while the other three mapping rules remain contextual-only.

After review, omit `--dry-run` to persist claims and materialize the canonical risk view.

## Source/identity guarantees

The backfill does not modify DPC source records and does not perform identity reconciliation. DPC remains a risk-evidence source only.

The canonical count and identity graph must therefore remain unchanged by a DPC risk backfill.
