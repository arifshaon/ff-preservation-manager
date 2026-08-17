# Risk frameworks

A risk framework defines **which preservation questions are asked, which evidence fields may answer them, how controlled answers map to points, and whether an overall risk band may be emitted**.

Framework files are JSON and are loaded by `frameworks.py`.

## Minimal structure

```json
{
  "framework_id": "example",
  "version": "1.0",
  "unknown_answer_id": "unknown",
  "calibration_status": "calibrated",
  "scale": {
    "direction": "higher_is_risk",
    "banding_enabled": true,
    "min_completeness_for_band": 0.67,
    "bands": [
      {"band": "Low", "min_score": 0, "max_score": 5},
      {"band": "Moderate", "min_score": 6, "max_score": 12},
      {"band": "High", "min_score": 13, "max_score": 30}
    ]
  },
  "questions": []
}
```

## Framework metadata

### `framework_id`

Stable identifier for the framework.

### `version`

Version of the framework definition. Reports should retain both ID and version.

### `calibration_status`

Describes governance/calibration state. The current broad QNL question framework uses:

```text
draft_unvalidated
```

This field is descriptive; overall banding is controlled explicitly by `scale.banding_enabled`.

### `source_basis`

Optional human-readable provenance for the framework design.

## Scale

### `direction`

Allowed values:

```text
higher_is_risk
lower_is_risk
```

The framework must state the direction rather than requiring callers to infer it.

### `banding_enabled`

When `false`, the engine still derives question answers, points and completeness, but emits:

```text
analysed_band = null
band_suppressed_reason = framework_not_calibrated
```

Use this while a question set is operationally useful but its overall score/bands are not yet approved.

### `min_completeness_for_band`

A number from 0 to 1.

The scorer calculates:

```text
answered non-abstention questions / total framework questions
```

If completeness is below the threshold, banding is suppressed.

Be precise when expressing fractions. For example, `0.67` is slightly greater than exact two-thirds (`0.6666...`). If the policy intent is exactly two of three questions, define and test the threshold deliberately.

### `bands`

Bands must not overlap. Each has:

```json
{
  "band": "Low",
  "min_score": 0,
  "max_score": 5
}
```

## Questions

Example:

```json
{
  "id": "q_external_assets",
  "label": "Does opening or rendering the file depend on external assets or services?",
  "domain_id": "software_dependencies_environment",
  "domain_label": "Software Dependencies & Environment",
  "definition": "Assesses non-embedded dependencies required for use.",
  "guidance": "Embedded resources do not count merely because the format supports embedding.",
  "aliases": ["external dependencies", "linked resources"],
  "critical": true,
  "weight": 2,
  "evidence_fields": ["sustainability.external_dependencies"],
  "evidence_value_map": {
    "none": "low_risk",
    "moderate": "moderate_risk",
    "high": "high_risk"
  },
  "answers": [
    {"id": "low_risk", "label": "Self-contained/common dependencies", "points": 0},
    {"id": "moderate_risk", "label": "Manageable dependencies", "points": 1},
    {"id": "high_risk", "label": "Fragile/specialist external dependencies", "points": 2},
    {"id": "unknown", "label": "Insufficient evidence", "points": 0, "abstention": true}
  ]
}
```

## Question fields

### `id`

Stable machine identifier. Integrations should filter by question ID rather than question wording.

### `label`

Human-facing question wording.

### `domain_id` / `domain_label`

Used to organize the broader question set and enable domain-specific assessment.

### `definition` / `guidance`

Clarify semantics so deterministic mappings and AI review do not over-interpret a criterion.

### `aliases`

Alternative human terms used by the natural-language request router.

### `critical`

If a critical question abstains, overall banding is suppressed with:

```text
critical_abstention
```

### `weight`

Multiplies answer points.

### `evidence_fields`

Only these criterion/evidence fields may answer the question.

The engine does not infer from unrelated registry fields.

### `evidence_value_map`

Question-local mapping from normalized criterion values to controlled answer IDs.

This is preferred for new frameworks because the same neutral criterion can be interpreted differently by different framework designs without changing the registry vocabulary.

### `applicability`

Optional content-type restriction, for example:

```json
"applicability": ["image", "graphics"]
```

This supports content-specific essential-characteristics questions.

## Answers

Each answer requires:

```text
id
points
```

Optional fields include:

```text
label
definition
guidance
abstention
```

At least one unknown/abstention answer is strongly recommended so missing evidence is explicit rather than silently converted to a substantive answer.

## Framework validation rules

The loader rejects common structural errors such as:

- missing framework ID;
- no questions;
- duplicate question IDs;
- question with no answers;
- duplicate answer IDs;
- nonnumeric/nonpositive weights;
- `evidence_value_map` pointing to unknown answer IDs;
- invalid scale direction;
- overlapping bands;
- completeness threshold outside 0..1.

## Current examples

### `qnl_sustainability.framework.example.json`

Small three-question example used to test deterministic scoring/banding.

It is **not** the final QNL preservation-risk model.

### `qnl_preservation_risk_questions.framework.draft.json`

Broad 8-domain / 22-question working framework.

It is intentionally:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

Use it for evidence collection, question-level assessment, gaps and remediation. Do not present its overall risk bands as approved QNL policy.

## Adding a new criterion versus adding a framework question

These are different changes.

```text
criteria vocabulary
  = neutral evidence observations

risk framework
  = interpretation of those observations as risk questions/answers
```

If a source introduces an observation not represented by the neutral vocabulary, first update the builder criterion vocabulary and mapping. Then bind that criterion to a framework question if it should affect assessment.

See the registry-builder guide:

[`../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

## Governance rule

Changing weights, answer points, critical flags, completeness thresholds, band boundaries or `banding_enabled` changes policy behavior. Treat those as reviewed framework changes, not incidental code edits.

## Related docs

- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
