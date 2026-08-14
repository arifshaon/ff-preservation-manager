# Identifier Reconciliation Rules

This note records the grouping fixes made after reviewing early QNL workbook output.

## 1. Workbook columns must be explicitly mapped

Source adapters for manually maintained files must not use substring matching over column names. In the QNL policy workbook, the format-name column is `Digital file`, while `QNL Format ID` also contains the word `format`. A fuzzy fallback such as `format in qnl_format_id` can silently bind the name field to the ID column.

Use source configuration instead:

```json
{
  "field_map": {
    "name": "Digital file",
    "source_id": "QNL Format ID",
    "extensions": "File Extension(s)"
  }
}
```

If a configured column is absent, the adapter must fail loudly rather than guessing.

## 2. Identifier claims carry provenance

Identifiers are stored as source-specific claims:

```python
Identifier(kind="puid", value="fmt/44", source="institution_policy_xlsx", verified=False)
Identifier(kind="puid", value="fmt/44", source="pronom_registry", verified=True)
Identifier(kind="puid", value="fmt/44", source="pronom_droid_xml", verified=True)
Identifier(kind="nara", value="NF00143", source="nara_digital_preservation_framework", verified=True)
```

A PUID copied into a spreadsheet is evidence, but not an authoritative identifier. A PUID from PRONOM source data is authoritative for reconciliation.

## 3. Strong identifiers vs weak identifiers

Strong grouping identifiers:

- verified PUID from PRONOM source data, such as `pronom_registry` or `pronom_droid_xml`;
- verified LOC FDD ID from LOC FDD data;
- verified NARA ID from NARA Digital Preservation Framework data.

Weak identifiers:

- MIME type;
- extension;
- unverified PUID copied from a spreadsheet;
- PUIDs copied from another authority's URL, such as a PRONOM URL inside NARA data;
- unverified LOC/NARA IDs copied from a non-authoritative source.

Weak identifiers may be stored, displayed, and used as supporting evidence, but they must not be primary grouping keys.

## 4. MIME type must never be a primary key

MIME types can describe broad classes rather than one exact format. For example, `text` can apply to many structured scientific formats. Grouping by MIME type would merge unrelated formats and corrupt downstream risk, readiness, and method-profile assignment.

## 5. Hazard is reconciled after grouping

The hazard reconciler is called after records are grouped into canonical formats. It reconciles external and institutional estimators without adding them together:

```text
external hazard estimator + institutional hazard estimator -> reconciled hazard assessment
```

The output records whether the basis is `external_only`, `institution_only`, `corroborated`, or `institution_override`, and it flags divergence for review.

This should run only after safe grouping, because hazard reconciliation over incorrectly merged formats produces confident nonsense.

## 6. Conservative weak bridging

Verified authority identifiers still dominate reconciliation. However, institutional rows often lack NARA or PRONOM identifiers. To support real external-vs-institutional reconciliation, the reconciler permits a narrow bridge:

```text
name + extension
```

This bridge can alias a weak institutional/non-authority group to a verified authority group only when it uniquely connects records across different sources and exactly one candidate group has a verified strong identifier.

If two authority groups share the same weak key, the bridge does not merge them.
