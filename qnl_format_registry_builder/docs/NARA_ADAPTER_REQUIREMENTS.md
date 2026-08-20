# NARA Adapter

NARA is the first high-value external hazard source because it turns real workbook runs from `institution_only` into actual external-vs-institutional reconciliation.

The preferred source-level adapter is:

```text
nara_digital_preservation_framework
```

The older adapter name remains available only as a deprecated compatibility alias:

```text
nara_preservation_csv
```

CSV is not the architectural boundary. CSV is simply the current implemented retrieval mode for the NARA Digital Preservation Framework source.

## Current retrieval mode

Implemented retrieval mode:

```text
published_csv
```

The adapter parses NARA Digital Preservation Framework CSV exports, including the preservation action plan and numbered risk matrix:

```text
Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_<YYYYMMDD>.csv
Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_<YYYYMMDD>_Numbered.csv
```

The action-plan CSV contains format names, extensions, categories, NARA format IDs, risk levels, preservation actions, proposed preservation plans, and preferred tools. The numbered risk-matrix CSV contains the native numeric risk rating and related score fields.

Future retrieval modes, such as an API, linked-data endpoint, or other structured NARA source, should be added inside `nara_digital_preservation_framework` rather than creating a new source concept for each file representation.

## Release modes

The NARA adapter supports three explicit release modes.

### Pinned release

Use this for reproducible/audit runs:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "retrieval_mode": "published_csv",
  "release_mode": "pinned",
  "release_date": "20260320",
  "github_ref": "master"
}
```

The adapter resolves the two dated CSV paths for that release. No source URLs need to be duplicated in the config.

### Latest release

Use this for quarterly refresh runs:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "retrieval_mode": "published_csv",
  "release_mode": "latest",
  "github_ref": "master"
}
```

Online `latest` mode reads NARA's GitHub contents listings, finds the highest release date where both the action-plan CSV and numbered-risk CSV exist, then snapshots those files. The resolved release is cached in:

```text
work/snapshots/<source_id>/.nara_release_index.json
```

Offline `latest` mode reuses that cached release index and then reads the cached source snapshots. If no cached release index exists, it fails loudly.

### Explicit URIs

Use this only when testing special files or non-standard locations:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "retrieval_mode": "published_csv",
  "release_mode": "explicit_uris",
  "uris": [
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv",
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv"
  ]
}
```

## Release metadata

Each NARA source snapshot carries release metadata where available:

```json
{
  "release_mode": "latest",
  "release_date": "20260320",
  "kind": "risk_matrix_numbered",
  "github_ref": "master",
  "github_path": "Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
  "github_blob_sha": "..."
}
```

The same metadata is also copied into NARA row evidence and raw record metadata. This lets change detection distinguish source-content movement from adapter/configuration movement.

## Why NARA matters

The reconciler can compare two estimators, but an institutional workbook alone supplies only one estimator: the local institutional risk level.

With NARA enabled, the following assessment paths become real operational outputs:

- `external_only`
- `corroborated`
- `institution_override`
- divergence detection
- review-required signals

## Preserve NARA native rating

NARA's numeric rating must not be collapsed into only `Low`, `Moderate`, or `High`.

The adapter emits both a normalized value for the current reconciler and native NARA evidence for future calibration/trend analysis:

```json
{
  "external_band": "Moderate",
  "rating": 2.0,
  "normalized_rating": 2.0,
  "external_rating_native": -12,
  "external_rating_native_scale": "nara_file_format_risk_matrix",
  "external_rating_native_direction": "higher_is_safer",
  "native_rating_band": "Moderate",
  "native_band": "Moderate Risk"
}
```

The normalized value supports current Low/Moderate/High reconciliation. The native value remains available for trend calculation, calibration, threshold analysis, and explaining edge cases such as nearly-High or barely-Moderate formats.

The reconciled `hazard_assessment` also carries these native fields when available:

```json
{
  "basis": "institution_override",
  "external_rating": 2.0,
  "institution_rating": 1.0,
  "external_rating_native": 22.0,
  "external_rating_native_direction": "higher_is_safer",
  "external_native_gap_to_institution_band": 1.0
}
```

`external_native_gap_to_institution_band` is a review aid only. It is the distance from the NARA native rating to the nearest threshold for the institution's band. It is not used as the normalized hazard score.

## Direction and cutoffs

NARA's native numeric direction is inverted relative to intuitive hazard scoring: higher means safer. The adapter records this explicitly:

```json
{
  "external_rating_native_direction": "higher_is_safer"
}
```

No downstream logic should assume that a larger native source rating always means higher hazard.

Current native-to-band mapping:

```python
def nara_band(rating: float) -> str:
    if rating >= 23:
        return "Low"
    if rating <= -23:
        return "High"
    return "Moderate"
```

The native value must not be read by `_hazard_score_from_dict()` as a direct hazard score, because that would reverse the meaning of the scale.

## Identifier authority

The NARA adapter treats `NARA Format ID` values such as `NF00143` as verified NARA identifiers.

PRONOM URLs inside the NARA data are retained as useful identifier claims, but the NARA adapter does not make those PUIDs verified PRONOM identifiers. Verified PUID authority comes from PRONOM itself, for example `pronom_registry` or `pronom_droid_xml`.

## Reconciliation behavior

NARA records normally have verified NARA IDs, while institutional spreadsheet rows usually do not. To let the two sources meet safely, the reconciler supports a conservative weak bridge:

```text
name + extension
```

This bridge is used only when it uniquely connects one institutional/non-authority group to exactly one verified authority group across different sources. If two authority groups share the same weak key, the bridge does not merge them.

## Validation expectations

The adapter and reconciler now have regression tests for:

- pinned/latest/explicit NARA release resolution;
- native numeric rating preserved;
- native direction preserved;
- normalized band/rating supplied separately;
- native rating copied into reconciled hazard assessment;
- NARA ID verified as a NARA identifier;
- PUIDs from NARA PRONOM URL kept unverified;
- NARA + institutional agreement produces `corroborated`;
- ambiguous weak matches do not merge multiple NARA authority records.

## Which risk-matrix view to ingest

NARA publishes the risk matrix twice, `..._Labeled.csv` and `..._Numbered.csv`.
**The adapter reads the Labeled view.** Both files carry identical values in all
20 non-rubric columns — every aggregate score, band and total — and differ only
in how the 27 rubric answers are written, so the choice costs nothing and gains
two things.

**The numbered view cannot say "Unknown".** NARA's own weights file
(`NARA_File_Format_Risk_Matrix_Weights_*.csv`) documents the encoding:

```text
1.1  Is the format proprietary?     -1 = Yes or Unknown,  2 = No
1.2  Published open specification?   2 = Yes, -2 = No or Unknown
2.2  Actively maintained?            2 = Yes, -1 = No or Unknown
```

In **26 of the 27 questions** the numeric value fuses Unknown with the
risk-increasing answer. That is a sound scoring choice — uncertainty ought to
count against a format's score — and a poor evidence record, because read as
evidence it asserts findings NARA explicitly declined to make. Mapping the
numbered view produced 566 claims stating a definite value for cells NARA had
marked Unknown, 326 of them on `sustainability.tpm_encryption` alone.

**The numbered view also destroys question 1.4.** It buckets the specification
year into a score (`0` = ≤5 years, `-2` = 6-15, `-4` = 16+ **or Unknown**). The
labeled view keeps 499 real years spanning 1975-2025 — the input a
specification-age term needs, and unrecoverable from the score.

A further trap the labeled view removes: the numbers are risk *contributions*,
not answers, so 12 of the 27 questions are reverse-scored (`1.1` scores Yes as
`-1` and No as `2`). Every numeric mapping rule had to know its column's
polarity. `Yes`/`No`/`Unknown`/`N/A` cannot be got wrong.

### Unassessed markers

NARA marks a cell it did not decide three ways, and all three map to `unknown`:

| Marker | Where |
| --- | --- |
| `Unknown` | labeled view |
| `0` | labeled view, the counterpart of the numbered view's `FALSE` |
| `FALSE` | numbered view and older exports |

`N/A` is **not** an unassessed marker. Most questions carrying it are conditional
("If the format requires compression, can it be lossy?"), where "not applicable"
is a real and informative answer.

### Derived fields

The labeled year is exposed as two native fields:

- `native_fields.specification_year` — the year itself, for temporal scoring
- `native_fields.specification_age_bracket` — NARA's own bands recomputed from
  the year (`5_years_or_less`, `6_to_15_years`, `16_plus_years`), measured
  against the NARA release rather than today so the band matches the one NARA
  scored and does not drift as the file ages on disk

### Back-compatibility

A `..._Numbered.csv` already dropped in an input folder still works and is
recognised as `risk_matrix_numbered`. If both views are supplied the labeled one
wins, because the two files share column names and a rubric cell must read
`Unknown` rather than a score that cannot express it.

## Mapping files and review state

Three NARA mapping files ship, and the difference between them is governance,
not content:

| File | Rules | Claim review status |
| --- | --- | --- |
| `...v1.approved.json` | 4 | `approved` — reviewed, attributed to QNL DCPA |
| `...v1.provisional.json` | 27 | `unreviewed`, except the 4 reviewed rules which keep their approval and attribution per-rule |
| `...v1.draft.json` | 27 | `needs_review` — the authoring scaffold |

`config/sources.nara.local.json` uses the **provisional** file, which is what
takes NARA from 4 criteria to 22 and the registry as a whole from 10 to 24 of 26.

The provisional file exists so promotion is visible rather than implicit. Its
rules were promoted to unblock downstream work, not reviewed, so they must not
inherit the approved file's committee attribution. Their claims carry
`review_status: "unreviewed"`, which the risk manager still consumes —
`unreviewed` is not in its excluded set — but which can be filtered, counted, or
re-examined before any institutional decision rests on them.

```bash
# how many claims are resting on unreviewed rules
python -c "import json;from collections import Counter;print(Counter(json.loads(l)['review_status'] for l in open('out/criterion_claims.jsonl')))"
```

To promote a rule properly: review it, move it into the approved file with a real
`decided_by`/`decided_at`, and drop it from the provisional file.
