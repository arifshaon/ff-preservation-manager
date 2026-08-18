# Composite risk index — end-to-end implementation plan

Implementation specification for the Component Design (Option b) composite
obsolescence risk index, with the six corrections identified during review.

Nothing here requires new data acquisition. All three upstream sources are
already harvested completely and stored faithfully — verified against upstream:
NARA 758/758 rows, PRONOM 2,558/2,558 signature records, LoC 598/599 FDDs. The
work is in the **mapping and scoring layers**, which currently interpret roughly
a fifth of what is stored.

## 0. Design contract

| Rule | Consequence |
| --- | --- |
| The score is advisory and additive | It never replaces framework scoring, banding, or band suppression |
| The score never enters an LLM prompt | Computed and attached entirely outside the AI boundary |
| Unknown is not Low | Thin coverage suppresses the tier; it never produces a reassuring one |
| Missing is not negative | An unassessed input is renormalized away, never scored as 0 |
| NARA is a comparator, not a term | Its band is retained beside the score, never summed into it |
| Every input is audited | Assessed vs imputed is recorded per input, and gates the tier |

## 1. Stage map

```text
[S1] Promote NARA mapping rules        config only, archivist review
        |  27 draft rules -> approved; 4 currently live
        v
[S2] Add PRONOM specification-currency proxy      new mapping rule
        |  lastUpdatedDate, 98% populated
        v
[S3] Interpret LoC sustainability prose           bounded fill-gaps, cited
        |  3,593 stored factor statements -> controlled values
        v
[S4] Component scorer (composite_risk v2)         code
        |  S_LoC / E_tool / A_spec / T_penalty, coverage-gated tier
        v
[S5] Divergence comparator                        code
        |  full 3x3 matrix vs NARA band
        v
[S6] Calibration                                  fit against 758 labels
        |  weights + tier boundaries, held-out evaluation
        v
[S7] CLI + docs + regression tests
```

S1, S2, S4, S5 are mechanical. S3 needs the AI provider. S6 needs S1–S5 complete.

## 2. Data mapping

### 2.1 Field encodings actually present in the registry

These are the encodings verified in the stored data. Two are implementation
traps and are called out explicitly.

| Input | Location | Encoding | Trap |
| --- | --- | --- | --- |
| NARA rubric items | `source_records.raw.row["1．4: When was…"]` | ordinal strings | **Key uses U+FF0E FULLWIDTH FULL STOP**, not `.` — `"1.4"` will not match |
| NARA 1.4 | as above | `0` / `-2` / `-4` | ordinal, **not years** |
| NARA 6.1 | as above | `2` / `0` / `-4` / `FALSE` | four-level, not boolean |
| NARA 6.2 | as above | `1` / `0` / `-1` / `FALSE` | 135 records hold the middle `0` |
| NARA 6.5 | as above | `1` / `-1` / `FALSE` | — |
| `FALSE` (any 6.x) | as above | literal string | **unassessed, not negative** — all 49 occurrences are "unspecified version" aggregate rows, present in NARA's own published CSV |
| NARA band | `canonical_formats.hazard_assessment.band` | `Low`/`Moderate`/`High` | may live on a strong-identity sibling record |
| LoC factors | `source_records.native_fields.sustainability_factors.*` | **free prose** | cannot be mapped mechanically; needs interpretation |
| PRONOM currency | `source_records.raw.record.lastUpdatedDate` | date string, 98% populated | a *registry edit* date — a proxy for spec age, must be labelled as such |

`withdrawnDate` (1 record) and `formatRisk` (0 records) are too sparse to use.

### 2.2 Rule promotion (S1)

The draft scaffold at
`config/criterion_mappings/nara_digital_preservation_framework.v1.draft.json`
already contains all 27 rules with correct `values` maps — including
`"FALSE": "unknown"`, which is the correct reading. Promotion means moving
reviewed rules into the `.approved.json` file and flipping `mapping_status`.

Currently live (4 of 27): 1.2 disclosure · 3.2 identifiability ·
6.1 renderer_availability · 8.3 tpm_encryption.

Priority order for review, by what unblocks the scorer:

| Rules | Criterion | Unblocks |
| --- | --- | --- |
| 6.1, 6.2, 6.5 | renderer_availability, open_source_tooling, creation_software_support | `E_tool` |
| 1.4 | specification_currency | `A_spec` (NARA path) |
| 2.1, 2.2 | adoption, maintenance | `C_adoption`, `S_LoC` factor 2 |
| 3.1 | transparency_readability | `S_LoC` factor 3 |
| 4.1 | self_documentation | `S_LoC` factor 4 |
| 5.1, 5.2 | hardware_dependency | `S_LoC` factor 5 |
| 7.1, 7.2 | ip_licensing | `S_LoC` factor 7 |

Keep the existing `excluded_from_criteria` list unchanged — excluding section
TOTALs and `NARA Risk Level` as "composite conclusion, already consumed as
external hazard estimator" is exactly the anti-double-counting discipline the
component design depends on.

Emitted claims already carry `source_field`, `source_value`, `mapping_rule_id`,
`directness`, `covers`, and `review_status`, so provenance needs no new work.

### 2.3 Controlled value → component score

```
C_k score maps (1.0 = sustainable). Values absent from a map leave the
criterion UNEVIDENCED — never defaulted.

sustainability.disclosure          public_specification 1.0 | partial 0.6
                                   proprietary_documented 0.4 | undocumented 0.0
sustainability.adoption            very_high 1.0 | high 0.9 | moderate 0.6
                                   low 0.2 | niche_or_declining 0.2
transparency_readability           transparent 1.0 | partially 0.6
                                   requires_specialist_tools 0.3 | opaque 0.0
self_documentation                 self_describing 1.0 | partially 0.5 | not 0.0
external_dependencies              none 1.0 | low 0.8 | moderate 0.4 | high 0.0
ip_licensing                       no_known_barrier 1.0 | limited_or_unclear 0.5
                                   known_constraint 0.1
tpm_encryption                     none_or_not_applicable 1.0 | known_constraint 0.2

E_tool inputs (each normalized to [0,1] over its own observed range)
  renderer_availability     renderers_available 1.0 | limited_or_unknown 0.5
                            no_known_renderer 0.0                    weight 0.40
  open_source_tooling       open_source_available 1.0 | unknown 0.5
                            no_open_source_tooling 0.0               weight 0.40
  creation_software_support currently_supported 1.0 | unknown 0.5
                            unsupported_or_legacy 0.0                weight 0.20

A_spec (years), in precedence order
  1. PRONOM lastUpdatedDate      -> (today - date).days / 365.25   [proxy]
  2. NARA specification_currency -> current_or_recent 2.0 | dated 10.0
                                    stale_or_legacy 20.0           [ordinal]
  3. unavailable                 -> None; the age term is dropped, not imputed
```

Any value of `unknown` maps to no score at all — it is treated as unassessed,
never as a midpoint and never as a zero.

## 3. The scorer (S4)

```python
def component_risk(claims, format_doc, config, related_docs=None):
    # --- 1. S_LoC over evidenced factors only -------------------------------
    factors = {}                       # criterion -> score in [0,1]
    for criterion in SEVEN_FACTORS:
        scores = [SCORE_MAP[criterion][normalise(c.value)]
                  for c in claims
                  if c.criterion_id == criterion
                  and normalise(c.value) in SCORE_MAP[criterion]]
        if scores:
            factors[criterion] = min(scores)      # conflict -> conservative

    if factors:
        total_w = sum(config.weight(k) for k in factors)      # renormalize
        s_loc = sum(config.weight(k) * v / total_w for k, v in factors.items())
    else:
        s_loc = None

    # --- 2. E_tool over ASSESSED items only ---------------------------------
    # Missing is renormalized away, never scored as 0. This is the fix for
    # "partial assessment read as confirmed absence".
    present = {name: (TOOL_MAP[name][normalise(c.value)], w)
               for name, w in TOOL_ITEMS.items()
               for c in claims
               if c.criterion_id == name and normalise(c.value) in TOOL_MAP[name]}
    if present:
        wsum = sum(w for _, w in present.values())
        e_tool = sum(v * w for v, w in present.values()) / wsum
        e_tool_assessed = len(present)            # 0..3
    else:
        e_tool, e_tool_assessed = None, 0

    # --- 3. A_spec, best available source ----------------------------------
    a_spec, a_spec_source = spec_age(claims)      # PRONOM date > NARA ordinal

    # --- 4. Terms. An unavailable input drops its term; nothing is imputed. -
    w_loc, w_tool, w_age = config.weights_for(
        has_loc=s_loc is not None,
        has_tool=e_tool is not None,
        has_age=a_spec is not None)               # renormalized to sum 1.0

    t_penalty = 0.0
    if a_spec is not None:
        damp = 1.0 - (c_adoption or 0.0) * (e_tool if e_tool is not None else 0.0)
        t_penalty = config.alpha * log(1.0 + a_spec) * damp

    raw = 100.0 * (w_loc * (1.0 - (s_loc or 0.0))
                 + w_tool * (1.0 - (e_tool if e_tool is not None else 0.0))
                 + w_age * t_penalty)
    score = clamp(raw, 0.0, 100.0)

    # --- 5. Tier is GOVERNANCE: emitted only when evidence supports it ------
    suppress = []
    if len(factors) < config.min_factors:      suppress.append("loc_coverage_below_minimum")
    if e_tool_assessed < config.min_tool_items: suppress.append("tooling_coverage_below_minimum")
    if s_loc is None and e_tool is None:        suppress.append("no_component_evidence")

    tier = None if suppress else config.tier_for(score)
    return Result(score=score, tier=tier, suppressed=suppress,
                  inputs=audit(factors, present, a_spec, a_spec_source), ...)
```

`c_adoption` is read from the `sustainability.adoption` factor already computed
in step 1 — never passed independently, so it cannot contradict `S_LoC`.

Every branch that would otherwise impute a value instead drops the term and
records the omission. There is no path on which an unassessed input silently
contributes a number.

## 4. Divergence comparator (S5)

Cover all nine cells, not two special cases. The current two-case rule reports
360 of 459 real disagreements as "Aligned".

```python
ORDER = {"Low": 0, "Moderate": 1, "High": 2}

def divergence(tier, nara_band):
    if tier is None or nara_band is None:
        return {"status": "not_comparable"}     # suppressed tier is not agreement
    d = ORDER[tier] - ORDER[nara_band]
    return {
        "status":    "aligned" if d == 0 else
                     "composite_higher" if d > 0 else "composite_lower",
        "magnitude": abs(d),                    # 1 = adjacent, 2 = opposite ends
        "composite": tier,
        "nara_band": nara_band,
        "priority":  abs(d) == 2,               # opposite-end disagreement
    }
```

Two honesty constraints. A suppressed tier yields `not_comparable`, never
`aligned` — absence of a verdict is not agreement. And divergence must **not**
be described as detecting NARA staleness while `E_tool` and `A_spec` derive from
NARA's own rubric: both sides move together, so it can only reveal NARA's
internal inconsistency. Genuine lag detection requires a tooling source
independent of NARA (COPTR, PRONOM software records, live probing) and should
be labelled as available only once such a source exists.

## 5. Calibration (S6)

Replace five invented constants — `w_LoC`, `w_tool`, `w_age`, and the 35/70
boundaries — with fitted ones. NARA's 758 expert-assigned bands are the labels;
this uses NARA once, at fit time, and never as a term in the sum.

```python
formats = sorted(nara_backed_formats)        # deterministic
Random(20260901).shuffle(formats)
holdout, fit = formats[:int(.20*n)], formats[int(.20*n):]   # split BY FORMAT

best = argmax over weight simplex (step 0.05, w summing to 1.0)
           and boundaries (low 25..45, high 55..85, step 5)
       of balanced_accuracy(predict(fit), nara_band(fit))

report(best, holdout)   # accuracy, per-band recall, confusion matrix
```

Report on the held-out fifth, never the fit set. Publish the confusion matrix
alongside the chosen constants so the calibration is auditable, and record the
fitted values with their fit date in the config rather than in code.

Success criterion: balanced accuracy materially above the majority-class
baseline (NARA is 63% Moderate, so anything at or below ~0.63 means the
components carry no signal). If it fails, that is a real finding — report it
rather than tuning until the number looks acceptable.

## 6. Interfaces

```
composite-risk --format <ref> [--institution ID] [--risk-config PATH]
               [--registry-json PATH | --storage-config PATH]

  ->  { composite_score, risk_tier | null, tier_suppressed_reasons[],
        terms{loc,tool,age}, divergence{status,magnitude,priority},
        inputs{ factors{}, tooling{assessed,imputed}, spec_age{value,source},
                nara{band,from_canonical_id} },
        authority_note }
```

`--risk-config` overrides `alpha`, factor weights, term weights, tier bounds,
and the coverage minimums. Fitted constants ship as the default config file.

## 7. Test plan

| Test | Guards |
| --- | --- |
| Formula matches an independently written reference across randomized inputs | Term drift, intermediate rounding |
| Fullwidth `1．4` key resolves; ASCII `1.4` also resolves via `alternate_fields` | The encoding trap |
| `FALSE` yields unassessed, not 0.0 | ASCII/HTML/CSS mandated for transformation |
| Partial tooling renormalizes over assessed items | Missing read as negative |
| No-evidence record emits no tier | "Unknown is Low" |
| Suppressed tier gives `not_comparable`, not `aligned` | False agreement |
| All nine divergence cells classified | The 360 silent disagreements |
| Conflicting claims take the conservative value | Optimistic conflict resolution |
| Calibration reported on held-out formats only | Fitting to the evaluation set |

Named regression fixtures: ASCII / HTML / CSS / Broadcast WAVE "unspecified
version" must never reach the High tier through the `FALSE` path.

## 8. Sequence and risk

| Step | Depends on | Type | Risk if skipped |
| --- | --- | --- | --- |
| S1 rule promotion | archivist review | config | Scorer keeps running on 2 of 7 factors |
| S2 PRONOM currency | S1 schema | config | `A_spec` stays a 3-level ordinal on 22% of formats |
| S3 LoC prose interpretation | provider | AI | 3,593 statements stay unused |
| S4 scorer | S1, S2 | code | — |
| S5 divergence | S4 | code | Disagreements stay invisible |
| S6 calibration | S1–S5 | analysis | Constants stay invented |
| S7 CLI/docs/tests | S4–S6 | code | — |

S4 and S5 can be built against the four currently-approved rules and will
improve automatically as S1 promotes more. S6 is the only step that cannot be
partially done — it needs the inputs stable first.
