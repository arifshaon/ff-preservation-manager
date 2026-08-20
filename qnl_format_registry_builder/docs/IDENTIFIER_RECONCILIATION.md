# Identifier Reconciliation Rules

This note records the grouping fixes made after reviewing early QNL workbook output.


## Records citing more than one authority

A source often cites identifiers it does not own so it can point at another
authority's record: NARA names both a PUID and a LOC FDD ID for the same format.
Those copied identifiers bridge the record onto the authority that owns them.

When the cited identifiers name **several** verified groups, the record cannot
join them all, and the rule is decided by identifier namespace:

```text
one cited group                  -> bridge to it
several, one strongest namespace -> bridge to that one; the others are NOT merged
several within one namespace     -> ambiguous; the record stays on its own
```

`identifier_kinds` order decides strength, so a PUID outranks a LOC FDD ID,
which outranks a NARA ID — PRONOM is the identification authority.

Refusing whenever more than one group is cited is tempting but wrong: it
discards the *uncontested* bridge as well. NARA's PUID links worked until LOC
was ingested and turned the cited FDD IDs into verified groups of their own, at
which point ~180 NARA records that PRONOM had correctly absorbed silently
detached. **Ingesting an authority must never undo an existing merge.**

Two things this deliberately does not do:

- It never merges the groups the record cited. NARA asserting that `fmt/356` and
  `fdd000254` are the same format is not PRONOM's or LOC's assertion, and a
  third party's crosswalk is not grounds for merging two authorities' records.
- It never picks between two formats in the same namespace. A record citing
  `fmt/1` and `fmt/6` is genuinely ambiguous about which format it means.

Every bridge chosen from several cited groups is marked
`confidence: heuristic`, and records left unattached because their citations were
ambiguous are listed by `collision-report` under
`ambiguous_identifier_citations`. That covers both authorities disagreeing
(NARA says Broadcast Wave v.0 is `fmt/1`, LOC's signature says `fmt/6`) and
family records that legitimately span several formats ("AIFF Family").

On the NARA -> PRONOM -> LOC sequence this holds 579 of the 592 NARA records
PRONOM absorbs, the remaining 13 being real NARA/LOC disagreements.


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
