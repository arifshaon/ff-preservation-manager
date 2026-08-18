"""Deterministic composite obsolescence risk index (blueprint alignment layer).

This implements the mathematical core of the neuro-symbolic architecture
blueprint: a single bounded obsolescence score computed *programmatically*,
before and independently of any LLM involvement.

    S_LoC       = sum_{k=1..7} w_k * C_k              (sum of weights = 1)
    R_composite = min(100, 100 * [ gamma1 * R_NARA
                                 + gamma2 * (1 - S_LoC)
                                 + alpha * ln(1 + A_spec) * (1.5 - E_tool) ])

where

    C_k     score in [0, 1] for one of the seven Library of Congress
            sustainability criteria (1 = sustainable), derived from
            normalized registry criterion claims;
    w_k     institutional weight for criterion k;
    R_NARA  numerical NARA baseline risk: Low = 0.2, Moderate = 0.5,
            High = 0.9, read from the registry's hazard assessment;
    A_spec  age in years since the format specification's last update,
            read from ``source.currency`` claims (stored as days);
    E_tool  open-source tool-availability index in [0, 1]
            (1 = robust multi-tool support, 0 = none);
    gamma1 = 0.45, gamma2 = 0.55, alpha = 0.08 by default.

Design boundaries, consistent with the rest of the package:

- The index is **advisory and additive**. It does not replace framework
  scoring, banding, or band suppression; it is attached alongside them.
- The LLM never receives or produces this score. The blueprint's own goal —
  deterministic, mathematically grounded assessment — is enforced by keeping
  the computation entirely outside the AI boundary.
- **Unknown is not Low.** Criteria without usable evidence are excluded and
  weights renormalized over evidenced criteria; when too few criteria are
  evidenced, or the NARA baseline is missing, the numeric score may still be
  reported but the risk tier is suppressed with an explicit reason.
- Conflicting claims for one criterion take the **minimum** (most
  conservative) score, mirroring ``derived_conflict_conservative``.
- ``E_tool`` currently has no registry source (Archivematica FPR ingestion is
  a roadmap item). It defaults to the neutral 0.5 — making the temporal term's
  ``(1.5 - E_tool)`` multiplier exactly 1.0 — and the default is flagged in
  the audit so consumers can see the input was assumed, not observed.

The tier boundaries are Low < 35 <= Moderate < ``high_min`` <= High. The
source blueprint's rendering of the Moderate/High boundary is unrecoverable
(the equation images are truncated); 65 is this implementation's default and
is deliberately configurable pending calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any

from preservation_risk_manager.errors import PreservationRiskManagerError


SEVEN_CRITERIA = (
    "sustainability.disclosure",
    "sustainability.adoption",
    "sustainability.transparency_readability",
    "sustainability.self_documentation",
    "sustainability.external_dependencies",
    "sustainability.ip_licensing",
    "sustainability.tpm_encryption",
)

CURRENCY_CRITERION = "source.currency"

# Sustainability score per normalized claim value (1 = sustainable, 0 = not).
# Values not listed leave the criterion unevidenced rather than guessing.
CRITERION_VALUE_SCORES: dict[str, dict[str, float]] = {
    "sustainability.disclosure": {
        "public_specification": 1.0,
        "partial_specification": 0.6,
        "proprietary_documented": 0.4,
        "undocumented": 0.0,
    },
    "sustainability.adoption": {
        "very_high": 1.0,
        "high": 0.9,
        "widely_adopted": 0.9,
        "moderate": 0.6,
        "low": 0.2,
        "niche_or_declining": 0.2,
        "declining": 0.2,
        "negligible": 0.1,
    },
    "sustainability.transparency_readability": {
        "transparent": 1.0,
        "partially_transparent": 0.6,
        "requires_specialist_tools": 0.3,
        "opaque": 0.0,
    },
    "sustainability.self_documentation": {
        "self_describing": 1.0,
        "partially_self_describing": 0.5,
        "not_self_describing": 0.0,
    },
    "sustainability.external_dependencies": {
        "none": 1.0,
        "low": 0.8,
        "moderate": 0.4,
        "high": 0.0,
    },
    "sustainability.ip_licensing": {
        "no_known_barrier": 1.0,
        "limited_or_unclear": 0.5,
        "known_constraint": 0.1,
    },
    "sustainability.tpm_encryption": {
        "none_or_not_applicable": 1.0,
        "known_constraint": 0.2,
    },
}

NARA_BAND_VALUES = {"low": 0.2, "moderate": 0.5, "high": 0.9}

DAYS_PER_YEAR = 365.25


class CompositeRiskError(PreservationRiskManagerError):
    """Raised when composite-risk configuration is invalid."""


@dataclass(frozen=True)
class CompositeRiskConfig:
    """Coefficients, weights, and governance thresholds for the index."""

    gamma1: float = 0.45
    gamma2: float = 0.55
    alpha: float = 0.08
    default_e_tool: float = 0.5
    low_max: float = 35.0
    high_min: float = 65.0
    # Tier floor. Measured against the 2026-08 registry export: of 1,379
    # formats with any of the seven criteria evidenced, 249 have 1, 897 have
    # exactly 2, and only 233 have 3+. A floor of 3 would suppress tiers for
    # ~83% of evidenced formats; since a missing NARA baseline already
    # suppresses the tier independently, 2 is the default and institutions
    # can tighten it in config.
    min_evidenced_criteria: int = 2
    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.default_e_tool <= 1:
            raise CompositeRiskError("default_e_tool must be between 0 and 1.")
        if not 0 < self.low_max < self.high_min <= 100:
            raise CompositeRiskError("Tier bounds must satisfy 0 < low_max < high_min <= 100.")
        if self.min_evidenced_criteria < 1:
            raise CompositeRiskError("min_evidenced_criteria must be at least 1.")
        unknown = set(self.weights) - set(SEVEN_CRITERIA)
        if unknown:
            raise CompositeRiskError(
                "Unknown criteria in weights: " + ", ".join(sorted(unknown))
            )
        if any(weight < 0 for weight in self.weights.values()):
            raise CompositeRiskError("Criterion weights must not be negative.")

    def weight_for(self, criterion: str) -> float:
        return float(self.weights.get(criterion, 1.0 / len(SEVEN_CRITERIA)))

    def tier_for(self, score: float) -> str:
        if score < self.low_max:
            return "Low"
        if score < self.high_min:
            return "Moderate"
        return "High"


def load_composite_risk_config(path: str | Path | None) -> CompositeRiskConfig:
    """Load coefficients/weights from JSON, or return blueprint defaults."""
    if path is None:
        return CompositeRiskConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CompositeRiskError("Composite risk config must be a JSON object.")
    try:
        return CompositeRiskConfig(
            gamma1=float(data.get("gamma1", 0.45)),
            gamma2=float(data.get("gamma2", 0.55)),
            alpha=float(data.get("alpha", 0.08)),
            default_e_tool=float(data.get("default_e_tool", 0.5)),
            low_max=float(data.get("low_max", 35.0)),
            high_min=float(data.get("high_min", 65.0)),
            min_evidenced_criteria=int(data.get("min_evidenced_criteria", 2)),
            weights={str(k): float(v) for k, v in (data.get("weights") or {}).items()},
        )
    except (TypeError, ValueError) as exc:
        raise CompositeRiskError(f"Invalid composite risk config: {exc}") from exc


def _normalise(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _claim_criterion(claim: dict[str, Any]) -> str | None:
    for key in ("criterion_id", "field", "evidence_field"):
        if claim.get(key) is not None:
            return str(claim[key])
    return None


def sustainability_score(
    claims: list[dict[str, Any]],
    config: CompositeRiskConfig,
) -> dict[str, Any]:
    """Compute S_LoC over evidenced criteria with renormalized weights."""
    per_criterion: dict[str, dict[str, Any]] = {}
    for claim in claims:
        criterion = _claim_criterion(claim)
        if criterion not in SEVEN_CRITERIA:
            continue
        value = _normalise(claim.get("value"))
        score = CRITERION_VALUE_SCORES[criterion].get(value)
        entry = per_criterion.setdefault(
            criterion, {"score": None, "values_seen": [], "unmapped_values": []}
        )
        if value and value not in entry["values_seen"] and value not in entry["unmapped_values"]:
            (entry["values_seen"] if score is not None else entry["unmapped_values"]).append(value)
        if score is None:
            continue
        # Conflicting evidence takes the most conservative reading.
        entry["score"] = score if entry["score"] is None else min(entry["score"], score)

    evidenced = {
        criterion: entry for criterion, entry in per_criterion.items()
        if entry["score"] is not None
    }
    total_weight = sum(config.weight_for(criterion) for criterion in evidenced)
    if evidenced and total_weight > 0:
        s_loc = sum(
            config.weight_for(criterion) * entry["score"] / total_weight
            for criterion, entry in evidenced.items()
        )
    else:
        s_loc = None

    return {
        "s_loc": None if s_loc is None else round(s_loc, 4),
        "evidenced_criteria": sorted(evidenced),
        "unevidenced_criteria": sorted(set(SEVEN_CRITERIA) - set(evidenced)),
        "coverage": f"{len(evidenced)}/{len(SEVEN_CRITERIA)}",
        "per_criterion": {
            criterion: per_criterion[criterion] for criterion in sorted(per_criterion)
        },
    }


def nara_baseline(
    format_doc: dict[str, Any],
    related_format_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read the NARA-scale baseline band from the format's hazard assessment.

    The band may live on a sibling canonical record (the registry keeps
    source-derived records such as ``nara-nf00380`` alongside PUID-anchored
    records) — the same strong-identity aliasing already used for criterion
    claims. When several linked records carry bands, the most conservative
    (highest-risk) one is used and the supplying record is audited.
    """
    best: dict[str, Any] | None = None
    for doc in [format_doc, *(related_format_docs or [])]:
        hazard = doc.get("hazard_assessment")
        if not isinstance(hazard, dict) or not hazard.get("band"):
            continue
        value = NARA_BAND_VALUES.get(_normalise(hazard["band"]))
        if value is None:
            continue
        candidate = {
            "r_nara": value,
            "band": str(hazard["band"]),
            "scale": hazard.get("external_rating_native_scale"),
            "basis": hazard.get("basis"),
            "source": "registry_hazard_assessment",
            "from_canonical_id": doc.get("canonical_id"),
        }
        if best is None or candidate["r_nara"] > best["r_nara"]:
            best = candidate
    if best is None:
        return {"r_nara": None, "band": None, "source": "hazard_assessment_missing"}
    return best


def spec_age_years(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive A_spec from the most recent ``source.currency`` claim (days)."""
    ages: list[float] = []
    for claim in claims:
        if _claim_criterion(claim) != CURRENCY_CRITERION:
            continue
        try:
            days = float(claim.get("value"))
        except (TypeError, ValueError):
            continue
        if days >= 0:
            ages.append(days)
    if not ages:
        return {"a_spec_years": None, "source": "currency_claims_missing"}
    return {
        "a_spec_years": round(min(ages) / DAYS_PER_YEAR, 2),
        "source": "source.currency",
        "currency_claims_seen": len(ages),
    }


def compute_composite_risk(
    format_doc: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    config: CompositeRiskConfig | None = None,
    e_tool: float | None = None,
    related_format_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute the composite obsolescence risk index for one format.

    Always returns the term-by-term breakdown and input audit. The numeric
    score is reported whenever any risk signal exists; the tier is suppressed
    (with reasons) when the inputs are too thin to govern by.
    """
    config = config or CompositeRiskConfig()
    if e_tool is not None and not 0 <= e_tool <= 1:
        raise CompositeRiskError("e_tool must be between 0 and 1.")

    sustainability = sustainability_score(claims, config)
    nara = nara_baseline(format_doc, related_format_docs)
    age = spec_age_years(claims)

    e_tool_value = config.default_e_tool if e_tool is None else float(e_tool)
    e_tool_audit = {
        "e_tool": e_tool_value,
        "source": "supplied" if e_tool is not None else "default_neutral_no_fpr_source",
    }

    s_loc = sustainability["s_loc"]
    r_nara = nara["r_nara"]
    a_spec = age["a_spec_years"]

    missing: list[str] = []
    if r_nara is None:
        missing.append("nara_baseline")
    if s_loc is None:
        missing.append("sustainability_evidence")
    if a_spec is None:
        missing.append("specification_age")

    if r_nara is None and s_loc is None:
        # No risk signal at all: a score here would be an invention.
        return {
            "status": "not_computable",
            "reason": "no_nara_baseline_and_no_sustainability_evidence",
            "inputs": {
                "sustainability": sustainability,
                "nara": nara,
                "specification_age": age,
                "tooling": e_tool_audit,
            },
        }

    nara_term = config.gamma1 * (r_nara if r_nara is not None else 0.0)
    sustainability_term = config.gamma2 * (1.0 - s_loc) if s_loc is not None else 0.0
    temporal_term = (
        config.alpha * math.log(1.0 + a_spec) * (1.5 - e_tool_value)
        if a_spec is not None
        else 0.0
    )
    score = round(min(100.0, 100.0 * (nara_term + sustainability_term + temporal_term)), 2)

    evidenced_count = len(sustainability["evidenced_criteria"])
    suppression: list[str] = []
    if r_nara is None:
        suppression.append("nara_baseline_missing")
    if evidenced_count < config.min_evidenced_criteria:
        suppression.append(
            f"sustainability_coverage_below_minimum_{config.min_evidenced_criteria}_of_7"
        )

    result: dict[str, Any] = {
        "status": "ok" if not missing else "ok_with_missing_inputs",
        "composite_score": score,
        "risk_tier": None if suppression else config.tier_for(score),
        "tier_suppressed_reasons": suppression,
        "missing_inputs": missing,
        "terms": {
            "nara_term": round(nara_term, 4),
            "sustainability_term": round(sustainability_term, 4),
            "temporal_term": round(temporal_term, 4),
        },
        "inputs": {
            "sustainability": sustainability,
            "nara": nara,
            "specification_age": age,
            "tooling": e_tool_audit,
        },
        "constants": {
            "gamma1": config.gamma1,
            "gamma2": config.gamma2,
            "alpha": config.alpha,
            "tier_bounds": {"low_max": config.low_max, "high_min": config.high_min},
        },
        "authority_note": (
            "Advisory composite index computed deterministically from registry evidence. "
            "It does not replace framework scoring, banding, or band suppression, and it "
            "is never supplied to or produced by AI components."
        ),
    }
    return result
