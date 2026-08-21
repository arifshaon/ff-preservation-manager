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

## Criterion projection

`config/criterion_mappings/loc_fdd_xml.v1.approved.json` maps the seven source-native factors into the neutral criteria vocabulary. The mappings are derived and partial: a criterion claim is created only when an approved value or conservative text rule matches the LOC prose.

The LOC mapping does not create a scalar LOC risk score, a hazard band, a preservation action, or a recommendation. LOC identity fields and cross-registry identifiers are excluded from criterion projection.

## Production integration

`config/sources.qnl.loc-sustainability.json` refreshes the reviewed `loc_fdd_xml` source contribution and applies only the approved LOC criterion mapping. Incremental source updates reuse the latest DPC, NARA, PRONOM, LOC crosswalk, and approved LOC-PRONOM bridge contributions already stored in MongoDB.

Before applying the mapping, run the read-only criterion evidence audit against the current persistent source records. After the LOC sustainability run, repeat the audit to inspect stored claim coverage and source-native field coverage.
