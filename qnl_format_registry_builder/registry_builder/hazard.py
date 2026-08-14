from __future__ import annotations

from typing import Any

BAND_TO_SCORE = {"Low": 1.0, "Moderate": 2.0, "High": 3.0}
SCORE_TO_BAND = [(1.49, "Low"), (2.49, "Moderate"), (3.0, "High")]


def score_to_band(score: float | None) -> str | None:
    if score is None:
        return None
    for upper, band in SCORE_TO_BAND:
        if score <= upper:
            return band
    return "High"


def reconcile_hazard(external_score: float | None, qnl_score: float | None, divergence_threshold: float = 0.5) -> dict[str, Any]:
    """Reconcile two estimators of intrinsic hazard without adding them.

    This implements the agreed principle: authoritative external assessment and
    QNL criteria assessment estimate the same latent quantity. They are not
    summed. Disagreement is surfaced as divergence and review need.
    """
    if external_score is None and qnl_score is None:
        return {
            "assessed": False,
            "band": None,
            "basis": "no_estimator_available",
            "confidence": "low",
            "divergence_flag": False,
            "review_required": True,
        }
    if external_score is None:
        return {
            "assessed": True,
            "rating": qnl_score,
            "band": score_to_band(qnl_score),
            "basis": "qnl_only",
            "confidence": "medium",
            "divergence_flag": False,
            "review_required": False,
        }
    if qnl_score is None:
        return {
            "assessed": True,
            "rating": external_score,
            "band": score_to_band(external_score),
            "basis": "external_only",
            "confidence": "medium",
            "divergence_flag": False,
            "review_required": False,
        }
    divergence = abs(external_score - qnl_score)
    if divergence <= divergence_threshold:
        return {
            "assessed": True,
            "rating": external_score,
            "band": score_to_band(external_score),
            "basis": "corroborated",
            "external_rating": external_score,
            "qnl_rating": qnl_score,
            "divergence": round(divergence, 3),
            "confidence": "high",
            "divergence_flag": False,
            "review_required": False,
        }
    return {
        "assessed": True,
        "rating": qnl_score,
        "band": score_to_band(qnl_score),
        "basis": "qnl_override",
        "external_rating": external_score,
        "qnl_rating": qnl_score,
        "divergence": round(divergence, 3),
        "confidence": "low",
        "divergence_flag": True,
        "review_required": True,
    }
