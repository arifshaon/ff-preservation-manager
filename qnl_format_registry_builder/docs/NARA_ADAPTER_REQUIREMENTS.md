# NARA Adapter Requirements

NARA is the next high-value source adapter because it provides an external hazard estimator. Until NARA is ingested, real QNL workbook runs will correctly report hazards as `qnl_only`.

## Why NARA matters

The current pipeline can reconcile two estimators, but the real QNL workbook currently supplies only one estimator: the QNL spreadsheet risk level. NARA adds an external baseline so the following assessment paths become real operational outputs rather than unit-test-only paths:

- `external_only`
- `corroborated`
- `qnl_override`
- divergence detection
- review-required signals

## Preserve NARA native rating

Do not collapse NARA's numeric rating into only `Low`, `Moderate`, or `High`.

The NARA rating should be stored in native form, for example:

```json
{
  "source_id": "nara_digital_preservation_framework",
  "source_type": "nara_lod",
  "native_rating": -12,
  "native_scale": "nara_obsolescence_rating_v1",
  "native_scale_min": -46,
  "native_scale_max": 37,
  "native_direction": "higher_is_safer",
  "native_band": "Moderate",
  "normalized_band": "Moderate",
  "normalized_rating": 2.0
}
```

The normalized band/rating can support current QNL Low/Moderate/High reconciliation, but the native value must remain available for trend calculation, calibration, threshold analysis, and explaining edge cases such as nearly-High or barely-Moderate formats.

## Direction matters

NARA's numeric direction is inverted relative to intuitive hazard scoring: higher means safer. The adapter must record this explicitly.

Recommended fields:

```json
{
  "native_rating": 14,
  "native_scale": "nara_obsolescence_rating_v1",
  "native_direction": "higher_is_safer"
}
```

No downstream logic should assume that a larger native source rating always means higher hazard.

## Mapping rule

The adapter should emit both:

```text
native source evidence
+ QNL-normalized reconciliation inputs
```

The normalized value is for current hazard-band reconciliation. The native value is for provenance, trend, calibration, and reporting.

## Reconciliation rule

NARA evidence should be treated as an external estimator of intrinsic format hazard. It should not be added to QNL's assessment. The reconciler should compare estimators, surface corroboration or divergence, and retain both original evidence trails.

## Validation expectations

A first NARA adapter implementation should include tests for:

- native numeric rating is preserved;
- native direction is preserved;
- normalized band/rating is supplied separately;
- NARA + QNL agreement produces `corroborated`;
- NARA + QNL disagreement produces divergence/review;
- missing QNL overlay produces `external_only`;
- NARA identifiers are treated as verified only for identifiers actually controlled or asserted by NARA/linked authority data.
