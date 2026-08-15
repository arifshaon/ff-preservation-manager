from __future__ import annotations

from typing import Any

REFRESH_PLANS = {
    "evidence": "rebuild_evidence_pack_and_rerun_analysis",
    "analysis": "rerun_analysis_and_action_resolution",
    "policy": "rerun_action_resolution_only",
}


def evaluate_recommendation_currency(
    stored: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Compare a stored recommendation against current evidence, analysis and policy.

    The three stale reasons are deliberately independent because each one has a
    different minimum refresh path.
    """
    currency = {
        "evidence_current": stored.get("evidence_hash") == current.get("evidence_hash"),
        "analysis_current": stored.get("analysis_result_id") == current.get("analysis_result_id"),
        "policy_current": stored.get("policy_hash") == current.get("policy_hash"),
    }
    stale_reason: list[str] = []
    if not currency["evidence_current"]:
        stale_reason.append("evidence")
    if not currency["analysis_current"]:
        stale_reason.append("analysis")
    if not currency["policy_current"]:
        stale_reason.append("policy")

    if not stale_reason:
        minimum_refresh = "none"
    elif stale_reason == ["policy"]:
        minimum_refresh = REFRESH_PLANS["policy"]
    elif stale_reason == ["analysis"]:
        minimum_refresh = REFRESH_PLANS["analysis"]
    elif stale_reason == ["evidence"]:
        minimum_refresh = REFRESH_PLANS["evidence"]
    else:
        minimum_refresh = "full_refresh"

    return {
        "recommendation_status": "stale" if stale_reason else "current",
        "stale_reason": stale_reason,
        "currency": currency,
        "minimum_refresh": minimum_refresh,
    }
