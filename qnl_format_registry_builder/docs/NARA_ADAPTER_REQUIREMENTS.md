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

It parses NARA Digital Preservation Framework CSV exports, including:

```text
Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv
Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv
```

The action-plan CSV contains format names, extensions, categories, NARA format IDs, risk levels, preservation actions, proposed preservation plans, and preferred tools. The numbered risk-matrix CSV contains the native numeric risk rating and related score fields.

Future retrieval modes, such as an API, linked-data endpoint, or other structured NARA source, should be added inside `nara_digital_preservation_framework` rather than creating a new source concept for each file representation.

## Why NARA matters

The reconciler can compare two estimators, but an institutional workbook alone supplies only one estimator: the local institutional risk level.

With NARA enabled, the following assessment paths become real operational outputs:

- `external_only`
- `corroborated`
- `institution_override`
- divergence detection
- review-required signals

## Recommended config

Enable NARA as a separate source alongside the institutional workbook:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "retrieval_mode": "published_csv",
  "uris": [
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv",
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv"
  ]
}
```

Using both CSVs is preferred. The preservation action plan gives the descriptive/action context; the numbered risk matrix gives the native numeric rating.

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

- native numeric rating preserved;
- native direction preserved;
- normalized band/rating supplied separately;
- native rating copied into reconciled hazard assessment;
- NARA ID verified as a NARA identifier;
- PUIDs from NARA PRONOM URL kept unverified;
- NARA + institutional agreement produces `corroborated`;
- ambiguous weak matches do not merge multiple NARA authority records.
