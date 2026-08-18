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
| Missing is not negative | An unassessed input is renormalized away, never scored as 0 — see decision 0.1 for NARA's `FALSE` marker |
| NARA is a comparator, not a term | Its band is retained beside the score, never summed into it |
| Every input is audited | Assessed vs imputed is recorded per input, and gates the tier |

## 0.1 Decisions

### 2026-08-18: NARA `FALSE` in rubric 6.x is unassessed, not a confirmed negative

**Decision:** treat the literal string `FALSE` in NARA rubric items 6.1, 6.2 and
6.5 as **unassessed**. It contributes nothing to `E_tool`, which is renormalized
over the items that were actually assessed. It is never read as a score of 0.0.

**Rationale:**

- All 49 occurrences carry `FALSE` in *all three* 6.x columns simultaneously,
  never partially, and 49 of 49 are "unspecified version" aggregate rows — the
  family placeholders where NARA did not complete a version-specific rubric.
  Verified against NARA's published CSV on GitHub, so this is a property of the
  source, not of ingestion.
- The affected formats include ASCII, HTML, CSS, GIF, Broadcast WAVE, TIFF,
  AutoCAD and Illustrator. Reading `FALSE` as "no renderers, no open-source
  tooling, no creation software" is factually wrong for every one of them.
- Under the rejected reading each scores 77.31 — above the 70 boundary, which
  triggers *mandatory transformation*. The system would order the normalization
  of HTML and ASCII.
- The decisive case is TIFF, where one family splits across both readings:

  ```text
  TIFF 1-6              6.x=(2,1,1)             E_tool=1.00    3.65  Low
  TIFF unspecified      6.x=(FALSE,FALSE,FALSE) E_tool=0.00   77.31  High
  TIFF-FX               6.x=(-4,0,-1)           E_tool=0.00   77.31  High
  ```

  TIFF-FX earns 77.31 from genuine assessed negatives and is scored correctly.
  TIFF unspecified reaches the identical number from an unfilled row. Under the
  rejected reading the two are indistinguishable in the output, so the system
  cannot tell "we checked and there are no tools" from "we never checked".
- The draft mapping rules already encode `"FALSE": "unknown"`, so this decision
  aligns the scorer with the mapping layer rather than diverging from it.

**Alternative considered and rejected:** keep `FALSE` → 0.0 as deliberate
policy, and exclude the 49 aggregate rows from the mandatory-transformation
trigger as a recorded false-positive class. Rejected because it preserves a
known-wrong input semantics and repairs the symptom downstream, leaving any
future consumer of `E_tool` exposed to the same error.

**Consequences:**

- `E_tool` is computed over assessed items only and renormalized by their
  weights; a missing item never contributes 0.
- The count of assessed tooling items is carried in the audit and gates the
  tier — an `E_tool` resting on too few assessed items suppresses the tier
  rather than producing one.
- Confirmed-negative ordinals (`-4`, `-1`) are unaffected and continue to drive
  `E_tool` toward 0, so genuine tool scarcity still escalates as intended.
- A named regression fixture pins the distinction: TIFF-FX must reach the High
  tier, TIFF/ASCII/HTML/CSS "unspecified version" must not reach it via the
  `FALSE` path.

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

Further sources (Wikidata linking, COPTR tooling, FPR recipes) plug in through
the existing adapter + criterion-mapping contract without changing the scorer —
see section 8.

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
    # "partial assessment read as confirmed absence", and it is where the
    # FALSE-is-unassessed decision (section 0.1) takes effect: TOOL_MAP has no
    # entry for FALSE, so such an item is simply absent from `present`.
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

Named regression fixtures, pinning decision 0.1 from both sides:

- **Must not** reach the High tier via the `FALSE` path: TIFF, ASCII, HTML, CSS,
  GIF and Broadcast WAVE "unspecified version".
- **Must** reach the High tier: TIFF-FX (`6.x = -4, 0, -1`), which earns it from
  genuine assessed negatives.

The pair is the test — if both sides do not hold, the scorer has stopped
distinguishing confirmed absence from unassessed data.

## 8. Source extensibility

The plan above names NARA, PRONOM, and LoC because those are the sources whose
data is already harvested and which the scorer's terms depend on. They are not
the closed set. This section records how further sources plug in, what Wikidata
specifically contributes, and the one rule the scorer must enforce regardless of
which sources are present.

### 8.1 The extension contract already exists

No new mechanism is needed. Adding a source is three pieces of configuration and
(only if the format is novel) one adapter class:

```text
1. adapter        registry_builder/adapters/<source>.py  subclassing SourceAdapter
                  -> registered by short name in ADAPTERS, OR shipped outside this
                     repository entirely and referenced as "package.module:ClassName"
                     (resolve_plugin already supports external adapters, so a
                     third-party source needs no core edit)

2. source config  sources.<name>.json
                  -> id, type, uris, offline flag, identifier_kinds

3. criterion map  config/criterion_mappings/<source>.v1.draft.json
                  -> rules promoted to .approved.json after archivist review,
                     identical schema and lifecycle to the NARA rules in S1
```

The scorer consumes `criterion_claims`, never sources directly. A new source
that emits claims for criteria the scorer already knows raises coverage with
**no scorer change at all**. That is the intended extension path and it is why
S4 is written against criteria rather than against NARA fields.

### 8.2 Wikidata — Tier 3, identity resolution

Wikidata is already modelled in the codebase, and deliberately not as an
evidence source:

```text
identifier_kinds:
  puid      strength=strong   verified_from=[pronom_registry, pronom_droid_xml, wikidata]
  loc       strength=strong   verified_from=[loc_fdd_xml]
  nara      strength=strong   verified_from=[nara_digital_preservation_framework, ...]
  wikidata  strength=weak     verified_from=[wikidata]
```

QIDs are marked **weak** and today arrive passively through NARA (666 records)
and LoC (340) crosswalks — 952 of 3,365 canonical formats (28%) carry one. There
is no Wikidata adapter; nothing queries SPARQL.

What a Wikidata adapter would add, measured rather than assumed:

| Measure | Value |
| --- | --- |
| Formats anchored to a single authority | **2,513 of 3,365 (74%)** |
| Formats with a QID but no PUID/NARA/LoC | 0 |

So Wikidata adds no *reach* — every format it knows about is already present —
but it is the natural instrument for the **fragmentation** problem: 74% of
formats are linked to only one authority, which is why PDF/A (`fmt/354`) cannot
see its own NARA record and why its composite tier is suppressed. Wikidata's
`P2749` (PRONOM ID), `P3267` (LoC FDD ID), and related properties are exactly
the join that is missing.

Its role therefore is:

- **In scope:** proposing links between existing canonical records, so claims
  already held under one authority reach a format anchored to another.
- **Out of scope:** contributing criterion claims. A crowd-maintained graph must
  not supply sustainability evidence on equal footing with a national archive.

Because QIDs are `weak`, a Wikidata-proposed link must not silently merge
records. It should be emitted as a **candidate link with provenance**, subject
to the same review lifecycle as a draft mapping rule, and the resulting claims
must remain attributable to their original authority rather than to Wikidata.

### 8.3 Operational sources — Tier 4

COPTR and release-pinned Archivematica FPR presets supply CLI invocation
templates and tool-capability observations. Two constraints:

- Command templates are **not criterion claims**. They belong in a migration
  pathways collection keyed by PUID, under institutional override
  (`local_fpr_rules.json`), and are never composed by an LLM.
- Tool-capability observations from COPTR *are* legitimate criterion evidence,
  and are the only route to a genuinely independent `E_tool`. Until such a
  source exists, `E_tool` derives from NARA's rubric and the divergence
  comparator therefore cannot claim to detect NARA staleness (see section 4).

### 8.4 The rule the scorer must enforce

Every claim already carries `source_id`, `directness`, `covers`,
`source_independence`, and `review_status`. The scorer must respect governance
tier when combining them:

```python
# Corroboration counts only across INDEPENDENT sources. Two claims that trace
# to the same authority are one observation, not two.
def corroboration(claims):
    return len({authority_of(c.source_id) for c in claims})

# A weak-tier source may corroborate a factor but must not be its sole basis.
def usable(claims_for_factor):
    return any(TIER[authority_of(c.source_id)] in ("identification", "evaluative")
               for c in claims_for_factor)
```

Without this, adding sources inflates apparent confidence: three claims from
three mirrors of the same authority would read as three independent
observations. The tier map belongs in config beside the weights, so adding a
source is still configuration rather than code.

### 8.5 Candidate sources, and what each would unblock

| Source | Tier | Would unblock | Status |
| --- | --- | --- | --- |
| Wikidata SPARQL | 3 linking | Cross-authority joins for 2,513 single-anchor formats | No adapter; QIDs arrive passively |
| COPTR | 4 operational | NARA-independent `E_tool`; real divergence detection | Not ingested |
| Archivematica FPR (pinned) | 4 operational | CLI templates for the migration layer | Not ingested; central registry decommissioned, use release-pinned presets |
| DPC Bit List | 2 evaluative | Trend / at-risk signal absent from all current sources | Suits the literature corpus (Corpus B) rather than a structured adapter |
| Institutional evidence | 2 evaluative, scoped | Local overlays | Already supported (`qnl_institution_format_evidence`) |

None of these blocks S1–S7. Each raises coverage of criteria the scorer already
consumes, which is the property the design is built to preserve.

## 9. Sequence and risk

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
