# Preservation risk analysis workflow

This document explains how one format moves from registry evidence to a deterministic preservation-risk result.

## End-to-end flow

```text
format query
 -> FormatResolver
 -> canonical format
 -> RegistryReader
 -> criterion_claims + retained format evidence
 -> evidence pack
 -> framework question matching
 -> deterministic answer derivation
 -> deterministic scoring
 -> band suppression checks
 -> risk result
 -> optional local posture / gap diagnosis / remediation
```

AI is not required for this path.

## 1. Resolve the format

`format_resolver.py` accepts canonical IDs, verified authority identifiers, names, aliases, MIME types and extensions.

Strong authority identifiers are preferred over weak discovery fields. Ambiguous matches are returned explicitly; the tool does not guess which format was intended.

## 2. Read evidence

`data_access.py` exposes `RegistryReader`, which queries the shared registry-store contract.

Two normal input modes exist:

### Persistent store

```powershell
--storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

This reads canonical formats and criterion claims from the same backend populated by the registry builder.

### Registry-builder exports

```powershell
--registry-json ..\qnl_format_registry_builder\output\registry.json
```

When export mode is used, the risk manager automatically looks beside `registry.json` for:

```text
criterion_claims.jsonl
criterion_claims.json
```

This is important because registry-builder exports canonical formats and normalized claims as separate files.

## 3. Assemble the evidence pack

`evidence_packs.py` combines:

- canonical format identity;
- global criterion claims;
- retained global/source evidence embedded in the canonical record;
- institution-scoped criterion claims when an institution is requested;
- migration/readiness evidence where present.

Global analysis excludes institution-scoped claims. Institution analysis includes global evidence plus claims for the requested institution only.

## 4. Derive controlled answers

`answer_derivation.py` evaluates only framework-declared `evidence_fields`.

For each question it can return states such as:

```text
derived
missing_evidence
unknown
derived_conflict_conservative
```

Important distinction:

- `missing_evidence` = no claim matched the question's required evidence fields;
- `unknown` = relevant claims matched, but none mapped safely to an allowed answer;
- `derived_conflict_conservative` = multiple valid claims disagreed and deterministic conflict handling selected the higher-risk controlled answer.

The engine does not infer answers from file names, extensions, general knowledge or unstated assumptions.

## 5. Score answers

`scoring.py` applies framework-declared:

- answer points;
- question weights;
- critical-question flags;
- completeness threshold;
- score bands;
- scale direction;
- calibration/banding status.

Typical result fields:

```text
score
max_score
analysed_band
analysis_status
evidence_completeness
missing_count
abstention_count
critical_abstention_count
band_suppressed_reason
```

## Analysis status

### `Assessed`

All questions received non-abstention answers.

### `Partially Assessed`

At least one question was answered, but one or more non-critical questions remain unknown/abstained.

### `Needs Assessment`

At least one critical question abstained.

### `Not Assessed`

No question received a substantive answer.

## Why a risk band may be `null`

A missing band is intentional. Inspect `band_suppressed_reason`.

### `framework_not_calibrated`

The framework has:

```json
"banding_enabled": false
```

Question-level assessment remains valid, but an overall Low/Moderate/High band is deliberately withheld.

### `not_assessed`

No substantive question could be answered.

### `critical_abstention`

A critical question remains unresolved.

### `insufficient_evidence_completeness`

The proportion of answered questions is below `min_completeness_for_band`.

Do not interpret a suppressed band as Low risk.

## Example deterministic command

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

## Evidence gaps

`evidence_gaps.py` separates several causes of incomplete assessment, including:

```text
no matching evidence
claims exist but do not map
claims exist but are unrelated to the active framework
```

These are available through machine requests such as:

```json
{
  "action": "list_evidence_gaps",
  "filters": {"family": "PDF"},
  "scope": "global"
}
```

## Remediation planning

`evidence_remediation.py` converts gaps into deterministic work types such as:

```text
mapping_rule_needed
source_evidence_needed
framework_alignment_review
```

with priorities based on factors such as critical-question blockage.

## Local institutional posture

`posture.py` combines the analysed band with separately supplied institutional readiness/exposure context. It does not rewrite the intrinsic/global format-risk evidence.

Keep these dimensions separate:

```text
format risk
local exposure
local readiness
local policy/action
```

## Related documentation

- [`FRAMEWORKS.md`](FRAMEWORKS.md)
- [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`../README.md`](../README.md)
