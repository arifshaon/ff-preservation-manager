# Registry-wide Risk / Evidence Audit

The registry audit evaluates the current canonical registry as a whole against a deterministic preservation-risk framework. It is designed to answer coverage and evidence-quality questions before adding more mappings or changing scoring logic.

## What it reports

The audit reports:

- total canonical formats and current criterion claims;
- how many formats answer 0, 1, 2, ... framework questions;
- deterministic band eligibility and Low / Moderate / High distribution;
- PUID-format band eligibility;
- per-question answered, abstained, missing-evidence, unknown-evidence, and conflict counts;
- criterion coverage by formats and contributing sources;
- source contribution, including how many formats/questions each source supports;
- conservative deterministic answer conflicts with source samples;
- LOC source relationship scopes (`exact_puid_cross_reference`, `multi_puid_source_record`, `version_ambiguous_puid_cross_reference`, etc.);
- sample formats with evidence gaps;
- optional draft mapping uplift: which unapproved mapping rules would add claims and, more importantly, potentially close currently unanswered risk questions.

The report is read-only. It never changes criterion mappings, canonical identities, deterministic answers, scores, bands, or institutional policy.

## Mongo-backed audit

From `preservation_risk_manager`:

```powershell
python -m preservation_risk_manager audit-registry `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --criteria ..\qnl_format_registry_builder\config\criteria\v1.json `
  --mappings-path ..\qnl_format_registry_builder\config\criterion_mappings `
  --out-dir registry-audit
```

This is the recommended command for QNL because the Mongo store contains the current canonical registry, criterion claims, and stored source records required to calculate draft mapping uplift.

Outputs:

```text
registry-audit\registry_risk_evidence_audit.json
registry-audit\registry_risk_evidence_audit.md
```

The JSON file is the machine-readable audit record. The Markdown file is a compact review report.

## Audit an exported registry

```powershell
python -m preservation_risk_manager audit-registry `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output-post-apply-check\registry.json `
  --out-dir registry-audit-export
```

`JsonRegistryStore` automatically discovers the sibling `criterion_claims.jsonl` or `criterion_claims.json` export when present.

Draft mapping uplift normally requires Mongo/source-record access. If the export does not include `source_records`, the audit reports the draft mapping section as unavailable rather than inventing an estimate.

## Reading the main sections

### `coverage_by_answered_questions`

For a three-question framework, this shows how many formats have deterministic answers for 0/3, 1/3, 2/3, or 3/3 questions.

### `band_eligible_formats`

A format is counted only when the existing scorer actually emits an `analysed_band`. The audit does not create a separate eligibility rule; it reuses the same deterministic derivation and scoring path as normal format assessment.

### `question_coverage`

For each framework question:

- `answered` means a non-abstention controlled answer was derived;
- `missing_evidence` means no matching criterion evidence was present;
- `unknown_with_matching_evidence` means matching evidence existed but could not yield an approved controlled answer;
- `conflicts` means multiple evidence claims yielded different controlled answers and the normal conservative conflict rule was applied.

### `source_contribution`

This distinguishes raw claim volume from actual framework support. A source can contribute many claims but support few current risk questions if those criteria are not used by the selected framework.

### `draft_mapping_opportunities`

When `--criteria` and `--mappings-path` are supplied, the audit recomputes claims twice from stored source records:

1. approved mappings only;
2. approved + draft mappings.

It then removes evidence already produced by approved mappings and ranks the remaining rules by:

1. potential currently-unanswered format/question gaps they could fill;
2. number of additional formats covered;
3. number of additional claims.

This is a review-prioritization metric only. Draft mappings remain unapproved and do not affect deterministic production scoring.

## Recommended review sequence

1. Review `coverage_by_answered_questions` and `question_coverage` to identify the main evidence bottleneck.
2. Review `source_contribution` to see which authorities currently support each risk question.
3. Review conflict samples before introducing source-precedence rules.
4. Review `loc_relationship_scopes` to ensure family/range evidence is not being treated as exact-version evidence.
5. Use `draft_mapping_opportunities.top_rules` to decide which draft mappings deserve human review next.
6. After approving or rejecting mappings, rerun the audit and compare the JSON reports.

Do not approve mappings merely because they increase coverage. Evidence scope, source semantics, format/version identity, and mapping meaning must remain defensible.
