# Multi-source preservation risk assessments

## Purpose

The registry retains preservation-risk assessments from each source independently and may also expose an optional synthesized semantic view for decision support.

The synthesized view never replaces, rewrites, averages, or hides the source-native assessments.

This matters because sources do not necessarily use the same vocabulary, scale, methodology, or scope. For example:

- NARA publishes a format-risk assessment and a native numeric risk matrix;
- DPC Global Bit List uses classifications such as Lower Risk, Vulnerable, Endangered, Critically Endangered, and Practically Extinct;
- an institution such as QNL may publish its own local Low/Moderate/High assessment;
- LOC FDD primarily contributes sustainability-factor evidence and does not provide one native overall preservation-risk classification for every FDD.

## Canonical record fields

Canonical records now have two preferred risk views:

```text
risk_assessments[]
    source-native assessments, retained independently

synthesized_risk
    optional semantic decision-support interpretation
```

The existing fields remain during migration:

```text
external_hazard
hazard_assessment
```

They are compatibility fields, not the preferred long-term query surface.

## Source-native assessment structure

A normalized wrapper around a source assessment may contain:

```yaml
assessment_role: external | institutional
source_id: nara_digital_preservation_framework
source_type: nara_digital_preservation_framework
source_record_id: NF00123
source_label: NARA Digital Preservation Framework

native_label: Moderate Risk
native_score: 12
native_scale: nara_file_format_risk_matrix

normalized_band: Moderate
normalized_score: 2
semantic_level: moderate
semantic_label: Moderate concern

scope_type: exact_format
scope_name: Portable Document Format 1.7
scope_basis: reconciled_source_record

native_assessment:
  # original source fields retained for audit
```

The wrapper does not redefine the original source assessment. `native_assessment` preserves the source-native data used to produce the query view.

## Assessment scope

Every mapped risk assertion should state what it actually applies to.

Recommended scope values are:

```text
exact_format
format_version
format_family
format_group
content_type
contextual
```

Scope is important when two sources appear to disagree.

Example:

```text
NARA: PDF/A-3 = Low
scope: exact_format

DPC: PDF = Vulnerable
scope: format_family
```

Those statements are not necessarily contradictory. The synthesized result therefore reports scope divergence and retains both source assessments.

## Shared semantic scale

The optional synthesis layer uses these deliberately broad semantic levels:

```text
minimal   -> Minimal concern
low       -> Low concern
moderate  -> Moderate concern
high      -> High concern
critical  -> Critical concern
```

Source-specific mappings into this scale must be explicit and reviewable. A source's native terminology remains stored unchanged.

The current pipeline can project its existing normalized Low/Moderate/High NARA and institutional bands directly to low/moderate/high semantic levels.

DPC terminology should be mapped by an approved DPC mapping configuration when the DPC adapter is enabled. Do not infer DPC semantics from title matching or numerical averaging.

LOC FDD sustainability factors should remain criterion evidence unless an explicit, reviewed method is introduced to derive an overall semantic risk from those factors. The system must not invent a LOC overall risk label.

## Synthesis method v1

`semantic_risk_synthesis_v1` is intentionally simple and transparent.

It:

1. retains every contributing assessment individually;
2. uses only assessments that have an explicit semantic mapping;
3. does not average native scores;
4. selects the highest mapped semantic concern as a conservative upper bound;
5. reports source divergence when mapped levels differ;
6. reports scope divergence when contributing assessments have different scopes;
7. lowers confidence when the semantic spread between sources is large;
8. lists the contributing source assessments in the synthesized result.

Example:

```yaml
risk_assessments:
  - source_label: NARA
    native_label: High
    semantic_level: high
    scope_type: exact_format

  - source_label: DPC Global Bit List 2025
    native_label: Vulnerable
    semantic_level: moderate
    scope_type: format_family

synthesized_risk:
  semantic_level: high
  semantic_label: High concern
  method: semantic_risk_synthesis_v1
  basis: conservative_semantic_upper_bound
  source_divergence: true
  scope_divergence: true
  explanation: >
    High concern selected as a conservative semantic upper bound from retained
    source assessments. Native assessments are not numerically averaged.
```

The conservative upper bound is a decision-support convention, not a claim that the source scales are mathematically equivalent.

## Query behavior

A query such as "what is the preservation risk of PDF?" should prefer the source-native view first:

```text
NARA: Moderate
DPC Global Bit List 2025: Vulnerable
LOC FDD: sustainability evidence available; no native overall risk classification
QNL: Low
```

If requested, the system can then show:

```text
Synthesized semantic risk: Moderate/High/etc.
Method: semantic_risk_synthesis_v1
Based on: <explicit contributor list>
Source divergence: yes/no
Scope divergence: yes/no
```

This keeps source truth auditable while still giving users a useful decision-support summary.

## Adapter guidance

New risk-bearing adapters should retain the source's native terminology and metadata. They should not calculate the cross-source synthesized result themselves.

The adapter or an approved source mapping should provide, when defensible:

```text
native_label
native_score/native_scale
semantic_level
scope_type
scope_name
```

Cross-source synthesis belongs to the registry risk-synthesis layer, after identity/scope mapping.
