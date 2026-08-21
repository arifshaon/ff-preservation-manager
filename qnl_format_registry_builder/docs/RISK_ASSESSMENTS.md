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

Canonical records have two preferred risk views:

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
scope: format_group
```

Those statements are not necessarily contradictory. A broad statement about PDF as a group must not silently override a more specific assessment of PDF/A-3.

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

DPC terminology is mapped by an approved DPC mapping configuration. Do not infer DPC semantics from title matching or numerical averaging.

LOC FDD sustainability factors remain criterion evidence unless an explicit, reviewed method is introduced to derive an overall semantic risk from those factors. The system must not invent a LOC overall risk label.

## Synthesis method v2: scope-aware conservative upper bound

`semantic_risk_synthesis_v2_scope_aware` replaces the original scope-blind v1 headline calculation.

The method first identifies the most specific available assessment tier:

```text
Tier 0  exact_format / format_version / institutional_format
Tier 1  format_family
Tier 2  format_group
Tier 3  content_type
Tier 4  contextual
Tier 5  unspecified
```

It then:

1. retains every source-native assessment independently;
2. uses only assessments that have an explicit semantic mapping;
3. selects the most specific available scope tier for the headline result;
4. within that tier, selects the highest semantic concern as a conservative upper bound;
5. never numerically averages native source scores;
6. retains broader-scope assessments as `contextual_contributors`;
7. reports `scope_divergence` when multiple declared scopes are present;
8. reports `source_divergence` only when assessments within the selected headline tier disagree semantically;
9. reports `cross_scope_level_divergence` when broader contextual assessments carry a different semantic level;
10. exposes the selected scope tier and scope types for audit.

This prevents a broad group-level assessment from changing a more specific headline risk merely because it has a higher semantic concern.

Example:

```yaml
risk_assessments:
  - source_label: NARA
    native_label: Low Risk
    semantic_level: low
    scope_type: exact_format
    scope_name: PDF/A-3

  - source_label: DPC Global Bit List 2025
    native_label: Vulnerable
    semantic_level: moderate
    scope_type: format_group
    scope_name: PDF

synthesized_risk:
  semantic_level: low
  semantic_label: Low concern
  method: semantic_risk_synthesis_v2_scope_aware
  basis: scope_aware_conservative_semantic_upper_bound
  selected_scope_tier: exact_or_version
  selected_scope_types:
    - exact_format
  source_divergence: false
  scope_divergence: true
  cross_scope_level_divergence: true
  contributors:
    - source_label: NARA
      native_label: Low Risk
      scope_type: exact_format
  contextual_contributors:
    - source_label: DPC Global Bit List 2025
      native_label: Vulnerable
      scope_type: format_group
```

The DPC assessment remains visible and queryable. It is not discarded; it simply does not override the more specific exact-format assessment.

## When broader evidence supplies the headline

If no more specific mapped assessment exists, the best available broader scope becomes the selected headline tier.

For example, if a PRONOM PDF/A record has no exact-format NARA or institutional assessment but is covered by the reviewed DPC PDF group mapping, the DPC `format_group` assessment may supply the current semantic headline. The result records:

```text
selected_scope_tier = format_group
```

This is preferable to reporting no semantic assessment at all, while still making the scope explicit.

## Relationship to synthesis method v1

The former `semantic_risk_synthesis_v1` selected the highest concern across every mapped assessment regardless of scope. That was intentionally conservative but could produce misleading headlines when broad and exact assessments differed.

For example:

```text
NARA exact PDF/A = Low
DPC PDF group = Vulnerable -> Moderate
```

v1 produced `Moderate` with `scope_divergence=true`.

v2 produces `Low` as the exact-format headline and retains DPC `Moderate` as broader contextual evidence.

The source-native records and mappings do not change; only the synthesized decision-support interpretation changes.

## Query behavior

A query such as "what is the preservation risk of PDF/A-3?" should prefer the source-native view first:

```text
NARA: Low Risk — exact format
DPC Global Bit List 2025: Vulnerable — broader PDF group
LOC FDD: sustainability evidence available; no native overall risk classification
QNL: <institutional assessment if available>
```

If requested, the system can then show:

```text
Synthesized semantic risk: Low
Method: semantic_risk_synthesis_v2_scope_aware
Selected scope: exact/version
Broader contextual concern: DPC PDF = Moderate
Source divergence at selected scope: no
Scope divergence: yes
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
