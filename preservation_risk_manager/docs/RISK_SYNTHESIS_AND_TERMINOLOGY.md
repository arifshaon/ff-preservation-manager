# Governed risk synthesis and terminology mapping

## Purpose

The Preservation Risk Manager keeps **source-native preservation-risk statements** separate from the common semantic vocabulary used for governed synthesis and AI-assisted analysis.

The governed business policy lives in:

```text
src/preservation_risk_manager/config/qnl_preservation_risk_synthesis.v1.json
```

The Python synthesis engine is an operator executor. Source names, native risk labels, semantic levels, scope precedence, headline-eligible roles, missing-evidence behavior and the selected synthesis operators are configuration data rather than source-specific `if NARA ...` / `if DPC ...` code.

This distinction matters:

```text
source-native evidence
        ↓
configured source rule
        ↓
common semantic level
        ↓
configured synthesis operators
        ↓
governed overall risk
        ↓
optional AI context + AI-assisted result
```

The original source-native statement remains available throughout this process.

## 1. Common semantic risk vocabulary

The vocabulary is declared by `semantic_levels` in the synthesis policy. The current QNL policy is:

| ID | Display label | Rank |
| --- | --- | ---: |
| `minimal` | Minimal concern | 0 |
| `low` | Low concern | 1 |
| `moderate` | Moderate concern | 2 |
| `high` | High concern | 3 |
| `critical` | Critical concern | 4 |

The rank is an ordering of **semantic concern**. It is not a conversion of source-native numeric scores and must not be used to average heterogeneous source scales.

The AI structured-output schema is generated from the configured `semantic_levels`. If the governed vocabulary changes, the AI is therefore given the same allowed semantic IDs.

## 2. Native terms are not globally translated

There is intentionally no global assumption such as:

```text
"Vulnerable" always means Moderate
"3" always means High
"At risk" always means High
```

A term has meaning only through a configured source rule or an explicitly accepted already-normalized `semantic_level`.

For example, the current DPC rule contains:

```json
{
  "rule_id": "dpc-global-bit-list",
  "source_match": {"source_type": "dpc_bit_list"},
  "role": "risk_assessment",
  "value_fields": ["native_label", "semantic_level"],
  "value_map": {
    "lower risk": "minimal",
    "vulnerable": "moderate",
    "endangered": "high",
    "critically endangered": "critical",
    "practically extinct": "critical"
  },
  "default_scope": "format_group"
}
```

Therefore:

```text
DPC native "Vulnerable"
    -> configured semantic "moderate"
    -> native label remains "Vulnerable"
```

An unknown DPC term remains **unmapped**. It is not guessed from wording.

## 3. NARA example

The current NARA persistence layer preserves the native NARA assessment and numeric score. The synthesis policy maps only the reviewed semantic labels:

```json
{
  "rule_id": "nara-native-risk",
  "source_match": {"source_id": "nara_digital_preservation_framework"},
  "role": "risk_assessment",
  "value_fields": ["native_label", "normalized_band", "semantic_level"],
  "value_map": {
    "low risk": "low",
    "moderate risk": "moderate",
    "high risk": "high"
  },
  "default_scope": "exact_format"
}
```

The NARA native score is retained for provenance. It is not averaged with DPC or another source's numbers.

## 4. Adding a new source-native risk vocabulary

Before a new source can influence governed overall risk:

1. Preserve its native risk statement, native scale and provenance in source/risk evidence.
2. Decide whether the source genuinely provides an overall preservation-risk assessment. Supporting evidence alone must not be promoted into a source-wide rating.
3. Identify the assessment scope (`exact_format`, `format_version`, `format_family`, `format_group`, etc.).
4. Review the source's vocabulary and define explicit mappings to configured `semantic_levels`.
5. Add a source-specific `source_rule` to the synthesis policy.
6. Add tests for every accepted native term plus at least one unknown term.
7. Review the result alongside existing sources before operational use.

Example:

```json
{
  "rule_id": "example-preservation-watchlist",
  "source_match": {"source_id": "example_watchlist"},
  "role": "risk_assessment",
  "value_fields": ["native_label"],
  "value_map": {
    "routine": "low",
    "watch": "moderate",
    "intervention required": "high"
  },
  "accept_existing_semantic_level": false,
  "default_scope": "format_family"
}
```

Do **not** add a generic keyword parser to infer mappings from unfamiliar wording.

## 5. Diagnostic mapping helper

The code exposes `map_risk_term()` so tests, diagnostics and future administration interfaces can check a native term using exactly the same configured source rules as normal synthesis.

Conceptually:

```python
map_risk_term(
    "Vulnerable",
    policy,
    source_context={"source_type": "dpc_bit_list"},
)
```

returns the configured semantic level and rule ID. An unknown term returns `mapped=false`.

## 6. Configurable synthesis operators

The `synthesis` section declares the business behavior. The current policy is:

```json
{
  "headline_roles": ["risk_assessment"],
  "missing_assessment_policy": "exclude",
  "scope_precedence": [
    ["exact_format", "format_version", "institutional_format"],
    ["format_family", "family"],
    ["format_group", "group"],
    ["content_type"],
    ["contextual"]
  ],
  "scope_selection": "most_specific_available",
  "same_scope_aggregation": "highest_semantic_concern",
  "broader_scope_policy": "context_only",
  "numeric_aggregation": "forbidden_across_source_scales"
}
```

Supported execution operators currently include:

| Policy field | Operators |
| --- | --- |
| `scope_selection` | `most_specific_available`, `all_mapped_assessments` |
| `same_scope_aggregation` | `highest_semantic_concern`, `lowest_semantic_concern`, `majority_semantic_level` |
| `broader_scope_policy` | `context_only`, `include_in_headline` |
| `missing_assessment_policy` | `exclude`, `unassessed_if_any_unmapped` |
| `numeric_aggregation` | `forbidden_across_source_scales` |

An operator may be a simple string or a configuration object when it has options. For example:

```json
{
  "same_scope_aggregation": {
    "operator": "majority_semantic_level",
    "tie_break": "highest_semantic_concern"
  }
}
```

### What "fully configurable" means

Preservation-policy decisions are configuration. The executable algorithms are named, tested operators in code. The policy chooses among them and supplies their options.

If QNL later needs a genuinely new algorithm—for example a reviewed source-trust weighting model—the correct extension is to add one tested operator and select/configure it in JSON. Do not embed a new institutional policy decision in a source adapter or UI.

## 7. Default QNL scope behavior

Under the current policy:

```text
exact_format / format_version / institutional_format
    > format_family
    > format_group
    > content_type
    > contextual
```

At the selected scope, `highest_semantic_concern` is the configured conservative aggregator. Broader assessments remain visible as context.

For PDF 1.7:

```text
NARA exact_format: Low
DPC format_group: Vulnerable -> Moderate

configured selected scope: exact_format
configured governed result: Low
DPC remains visible contextual evidence
```

This outcome is produced by the policy configuration, not by source-name logic in the executor.

## 8. Missing and unmapped evidence

Current governed behavior:

```text
absent source assessment -> contributes nothing
unknown native term       -> remains unmapped
missing framework answer  -> does not imply Low
```

The normal QNL policy uses `missing_assessment_policy=exclude`. Missing evidence still appears in evidence-gap/completeness analysis and may reduce AI confidence; it does not silently become a risk rating.

## 9. Relationship to AI-assisted synthesis

The AI receives:

- the configured semantic vocabulary;
- source-native and governed evidence;
- configured source mappings;
- synthesis methodology;
- governed baseline;
- assessment framework.

The AI is asked to return its own `semantic_level` using the configured vocabulary. It may use provider capabilities, general knowledge or external research when available/useful, but it must not rewrite the stored source-native assessments.

The application keeps:

```text
governed_synthesis
AI-assisted synthesis
```

as separate results. The relation between their final semantic levels is computed by the application from configured semantic ranks rather than trusting prose such as "more concerning".

## 10. Governance checklist for policy changes

Before replacing an operational synthesis-policy version:

- preserve the previous policy file/version;
- validate all configured source terms map only to declared semantic levels;
- test unknown terms remain unmapped unless deliberately handled;
- test exact/group/family scope cases;
- test same-scope disagreement;
- test missing-source behavior;
- compare policy-derived results with the locked/current registry synthesis during migration;
- record the policy version in reports;
- do not rewrite source-native evidence merely to make a new policy produce a desired outcome.
