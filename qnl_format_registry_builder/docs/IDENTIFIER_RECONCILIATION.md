# Identifier Reconciliation Rules

This note records the grouping rules used by the QNL format-registry builder.

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

A PUID copied into a spreadsheet or another authority record is useful provenance, but it is not authoritative in that source. A PUID from PRONOM source data is authoritative for the exact PUID identity.

Copied strong identifiers are retained in `identifier_claims` and, where applicable, in `source_records.identifier_cross_references`. They are **not** copied into the canonical format's compact `identifiers` index, because that index represents exact resolver identity.

## 3. Strong identifiers vs weak identifiers

Strong grouping identifiers:

- verified PUID from PRONOM source data, such as `pronom_registry` or `pronom_droid_xml`;
- verified LOC FDD ID from LOC FDD data;
- verified NARA ID from NARA Digital Preservation Framework data.

Weak/cross-reference evidence includes:

- MIME type;
- extension;
- unverified PUID copied from a spreadsheet;
- PUIDs cited by another authority;
- unverified LOC/NARA IDs copied from a non-owning authority.

Cross-reference identifiers may be stored, displayed, and used for conservative linking, but they must not create a second exact owner for a strong identifier.

## 4. PUID-first cross-authority reconciliation

When a non-PRONOM authority record cites more than one authority identifier for the same format, the copied identifiers are not competing canonical identities.

For example, a NARA record may contain:

```text
NARA ID: NF00362          verified by NARA
PUID:    fmt/14           copied PRONOM cross-reference
LOC ID:  fdd000316        copied LOC cross-reference
```

and the registry may also contain verified authority records for both `fmt/14` and `fdd000316`.

The reconciler uses configured strong-identifier priority. With the current configuration, PUID is evaluated before LOC and NARA for copied cross-authority bridging. If the copied PUID resolves uniquely and the format names do not contain conflicting version discriminators, the NARA source record is merged into the PUID canonical format.

The lower-priority copied LOC ID is retained as provenance. Its presence must not prevent the NARA-to-PUID bridge.

This fixes the earlier failure mode where adding LOC to a run changed:

```text
NARA -> one PUID target
```

into:

```text
NARA -> PUID target + LOC target -> ambiguous -> no merge
```

and therefore stranded NARA evidence on a separate canonical record.

## 5. Multi-PUID authority records are relationships, not one PUID identity

Some authority records intentionally describe a range or family and cite several PUIDs. These records must not be collapsed into one arbitrarily selected PUID.

Instead, the authority record remains independently addressable by its owning authority ID and is attached to each explicitly cited verified PUID through source-record relationship metadata:

```json
{
  "relationship": "explicit_puid_cross_reference",
  "evidence_scope": "multi_puid_source_record",
  "related_puids": ["fmt/14", "fmt/15", "fmt/16", "fmt/17"]
}
```

Approved criterion mappings can then use that source record when assessing each linked PUID, while provenance continues to show that the evidence originated in a broader source record.

Single-PUID copied relationships still respect version-conflict guards. Broad/family records are not treated as exact PUID equivalents merely because one copied PUID appears somewhere in the source.

## 6. LOC identifiers must be scoped to the current FDD record

The LOC XML adapter must not scan related-format/reference subtrees as though their identifiers describe the current FDD.

PUID and Wikidata extraction therefore excludes metadata beneath elements such as:

```text
relatedFormat
relatedFormats
relationship
relationships
reference
references
seeAlso
```

This prevents a PUID mentioned only for a related format from becoming a cross-reference of the current LOC FDD and subsequently propagating evidence to the wrong canonical format.

## 7. Strong identifier uniqueness is a validation gate

A strong identifier in `CanonicalFormat.identifiers` is an exact canonical identity assertion. Therefore the same PUID, LOC ID, or NARA ID must not appear in the compact identifier index of more than one canonical record.

Registry validation treats this as an error:

```text
strong identifier puid:fmt/14 appears in multiple canonical records
```

This makes source-refresh reconciliation regressions fail the build instead of silently creating competing canonical identities.

## 8. MIME type must never be a primary key

MIME types can describe broad classes rather than one exact format. For example, `text` can apply to many structured scientific formats. Grouping by MIME type would merge unrelated formats and corrupt downstream risk, readiness, and method-profile assignment.

## 9. Hazard is reconciled after grouping

The hazard reconciler is called after records are grouped into canonical formats. It reconciles external and institutional estimators without adding them together:

```text
external hazard estimator + institutional hazard estimator -> reconciled hazard assessment
```

The output records whether the basis is `external_only`, `institution_only`, `corroborated`, or `institution_override`, and it flags divergence for review.

This should run only after safe grouping, because hazard reconciliation over incorrectly merged formats produces confident nonsense.

## 10. Conservative weak bridging

Verified authority identifiers still dominate reconciliation. However, institutional rows often lack NARA or PRONOM identifiers. To support real external-vs-institutional reconciliation, the reconciler permits a narrow bridge:

```text
name + extension
```

This bridge can alias a weak institutional/non-authority group to a verified authority group only when it uniquely connects records across different sources and exactly one candidate group has a verified strong identifier.

If two authority groups share the same weak key, the bridge does not merge them.
