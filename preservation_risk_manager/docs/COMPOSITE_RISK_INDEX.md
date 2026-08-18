# Composite obsolescence risk index

`composite_risk.py` implements the mathematical core of the neuro-symbolic
architecture blueprint: one bounded, deterministic obsolescence score per format,
computed from registry evidence **before and independently of any AI involvement**.

```text
S_LoC       = Σ (k=1..7)  w_k · C_k                        with Σ w_k = 1
R_composite = min(100, 100 · [ γ₁·R_NARA
                             + γ₂·(1 − S_LoC)
                             + α·ln(1 + A_spec)·(1.5 − E_tool) ])
```

| Symbol | Meaning | Registry source |
| --- | --- | --- |
| `C_k` | Score in [0,1] for one of the seven LoC sustainability criteria (1 = sustainable) | `criterion_claims` (`sustainability.*`) |
| `w_k` | Institutional weight for criterion k (default 1/7 each) | `--risk-config` |
| `R_NARA` | NARA baseline: Low = 0.2, Moderate = 0.5, High = 0.9 | `hazard_assessment` on the canonical record or a strong-identity sibling |
| `A_spec` | Years since the specification's last update | `source.currency` claims (stored as days; most recent wins) |
| `E_tool` | Open-source tool availability in [0,1] | **No source yet** — neutral 0.5 default until FPR ingestion lands |
| `γ₁, γ₂, α` | 0.45, 0.55, 0.08 | blueprint defaults, `--risk-config` overridable |

Risk tiers: `Low < 35 ≤ Moderate < 65 ≤ High`. The Low/Moderate boundary (35) is
the blueprint's. The Moderate/High boundary is **unrecoverable from the source
document** (its equation images are truncated at that value); 65 is this
implementation's default and is deliberately configurable pending calibration.

## The seven criteria and their value maps

The registry's `sustainability.*` criteria are exactly the seven Library of
Congress sustainability factors. Claim values map to `C_k` conservatively; values
not listed leave the criterion **unevidenced** rather than guessed:

| Criterion | 1.0 | intermediate | 0.0-ish |
| --- | --- | --- | --- |
| disclosure | public_specification | partial 0.6 · proprietary_documented 0.4 | undocumented 0.0 |
| adoption | very_high | high 0.9 · moderate 0.6 | low/niche 0.2 · negligible 0.1 |
| transparency_readability | transparent | partial 0.6 · specialist_tools 0.3 | opaque 0.0 |
| self_documentation | self_describing | partial 0.5 | not_self_describing 0.0 |
| external_dependencies | none | low 0.8 · moderate 0.4 | high 0.0 |
| ip_licensing | no_known_barrier | limited_or_unclear 0.5 | known_constraint 0.1 |
| tpm_encryption | none_or_not_applicable | — | known_constraint 0.2 |

Conflicting claims for one criterion take the **minimum** (most conservative)
score, mirroring `derived_conflict_conservative` in answer derivation.

## Governance: when the tier is withheld

The numeric score is reported whenever any risk signal exists; the **tier** is
governance and is suppressed with explicit reasons when the inputs are too thin:

- `nara_baseline_missing` — no NARA-scale hazard band on the record or any
  strong-identity sibling;
- `sustainability_coverage_below_minimum_N_of_7` — fewer evidenced criteria than
  the configured floor.

The floor defaults to **2**, measured against the 2026-08 registry export: of
1,379 formats with any of the seven criteria evidenced, 897 have exactly 2 and
only 233 have 3+. A floor of 3 would suppress tiers for ~83% of evidenced
formats while the NARA-band requirement already gates the tier independently.
Institutions can tighten this in `--risk-config`.

With neither a NARA band nor any sustainability evidence the result is
`not_computable` — a score there would be an invention.

Measured on the full export (3,365 current formats): 713 tiered
(151 Low / 253 Moderate / 309 High), 590 score-only with the tier suppressed,
2,062 not computable. Escalations against the NARA band are concordant and
auditable (e.g. NARA-Moderate formats escalate to composite-High when
sustainability evidence is strongly negative and the specification is stale).

## Boundaries

- **Advisory and additive.** The index does not replace framework scoring,
  banding, or band suppression; `composite-risk` is a separate command and the
  result carries an `authority_note` saying exactly that.
- **Outside the AI boundary.** The LLM never receives or produces this score.
  The blueprint's Phase 3 wording ("inject the calculated score into the prompt
  context") is deliberately **not** followed — see the deviations section in
  [`ARCHITECTURE.md`](ARCHITECTURE.md); the score would anchor the model's
  evidence interpretation and turn independent review into rationalization.
- **Every input is audited.** The result carries per-criterion scores and values
  seen, the supplying canonical record for the NARA band, the age source, and
  whether `E_tool` was supplied or defaulted.

## Usage

```bash
python -m preservation_risk_manager composite-risk \
  --registry-json output/registry.json \
  --format "fmt/354" \
  [--institution qnl] [--e-tool 0.8] [--risk-config risk.json]
```

`--risk-config` JSON may override `gamma1`, `gamma2`, `alpha`, `default_e_tool`,
`low_max`, `high_min`, `min_evidenced_criteria`, and per-criterion `weights`
(unlisted criteria keep the equal-share default).

## Known gaps, in priority order

1. **`E_tool` has no evidence source.** Archivematica FPR ingestion (roadmap)
   supplies it; until then the neutral default makes the temporal multiplier
   exactly 1.0 and is flagged in the audit.
2. **Identifier fragmentation limits NARA coverage.** PDF/A (`fmt/354`) has no
   linked `nara-*` sibling in the current registry build, so its tier is
   suppressed despite NARA assessing PDF/A. The blueprint's Wikidata
   cross-walk layer addresses exactly this.
3. **The Moderate/High boundary needs calibration** against institutional
   expectations; the source document's value is unrecoverable.
