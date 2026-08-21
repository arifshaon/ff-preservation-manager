# LOC FDD sustainability evidence

The LOC Format Description Documents (FDDs) contribute source-native sustainability evidence to the QNL format registry. LOC is treated as a criterion-evidence source, not as an overall preservation-risk estimator.

## Official top-level factors

The reviewed LOC projection uses the seven LOC sustainability factors:

1. Disclosure
2. Adoption
3. Transparency
4. Self-documentation
5. External dependencies
6. Impact of patents
7. Technical protection mechanisms

They are stored under `native_fields.sustainability_factors` using these keys:

- `disclosure`
- `adoption`
- `transparency`
- `self_documentation`
- `external_dependencies`
- `impact_of_patents`
- `technical_protection_mechanisms`

Some LOC FDD XML records expose a `documentation` element alongside the sustainability material. Documentation is preserved, but it is not modeled as an eighth top-level LOC factor. The reviewed projection stores it as supporting Disclosure evidence at:

`native_fields.sustainability_factor_details.disclosure.documentation`

The reviewed extractor accepts exact structured LOC factor labels only. It does not classify arbitrary free text merely because words such as `transparency`, `adoption`, or `technical protection` occur in prose. The current LOC XML tag `techProtection` is recognized as the Technical protection mechanisms factor.

## Criterion projection

`config/criterion_mappings/loc_fdd_xml.v2.approved.json` is the approved production mapping. It was frozen after a fresh 598-record LOC preview, seven-factor coverage review, regression testing, and manual review of high-impact IP/licensing classifications.

The mapping is deliberately partial. A criterion claim is created only when an accepted value or conservative text rule supports a normalized value. Relational statements such as `See WAVE`, long historical narratives, mixed licensing statements, and otherwise ambiguous prose may remain unmapped. Higher mapping coverage is not itself a goal.

The LOC mapping does not create a scalar LOC risk score, a hazard band, a preservation action, or a recommendation. LOC identity fields and cross-registry identifiers are excluded from criterion projection.

## Production integration

Production is intentionally a two-stage workflow.

### Stage 1: refresh source-native LOC evidence

Run:

```powershell
python -m registry_builder run `
  --config config/sources.qnl.loc-sustainability.json `
  --workdir work `
  --out out/loc-sustainability-refresh
```

This refreshes the reviewed `loc_fdd_xml` contribution in MongoDB while reusing the latest DPC, NARA, PRONOM, LOC crosswalk, and approved LOC-PRONOM bridge contributions. Criterion mapping is deliberately disabled during this pipeline run.

### Stage 2: apply approved criterion claims with source-level replacement

Run:

```powershell
python -m registry_builder criterion-claims backfill `
  --config config/loc_fdd_sustainability_backfill.production.json
```

The backfill uses `config/criterion_mappings/loc_fdd_xml.v2.approved.json` and `replace_source_claims=true`. Source-level replacement is required so a previously current LOC criterion claim is superseded when a later approved mapping/source refresh no longer produces it, including the case where a mapping rule produces zero claims.

## Reviewed preview baseline

The final pre-production preview used 598 reviewed LOC FDD records and generated 1,565 draft claims across all seven factors. Coverage was intentionally partial:

- Disclosure: 305 / 598 (51.0%)
- Adoption: 191 / 597 (31.99%)
- Transparency: 173 / 594 (29.12%)
- Self-documentation: 27 / 593 (4.55%)
- External dependencies: 217 / 592 (36.66%)
- Impact of patents: 354 / 596 (59.4%)
- Technical protection mechanisms: 298 / 590 (50.51%)

For IP/licensing, the final reviewed distribution was 169 `no_known_barrier`, 181 `limited_or_unclear`, and 4 `known_constraint`. The four high-impact cases were manually inspected before approval.
