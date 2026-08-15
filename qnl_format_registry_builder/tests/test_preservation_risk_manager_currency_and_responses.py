from __future__ import annotations

from preservation_risk_manager.currency import evaluate_recommendation_currency
from preservation_risk_manager.responses import build_global_response, has_local_fields


BASE_STORED = {
    "recommendation_id": "rec-1",
    "evidence_hash": "evidence-a",
    "analysis_result_id": "analysis-a",
    "policy_hash": "policy-a",
}


def test_policy_staleness_requires_action_resolution_only():
    result = evaluate_recommendation_currency(
        BASE_STORED,
        {"evidence_hash": "evidence-a", "analysis_result_id": "analysis-a", "policy_hash": "policy-b"},
    )

    assert result["recommendation_status"] == "stale"
    assert result["stale_reason"] == ["policy"]
    assert result["minimum_refresh"] == "rerun_action_resolution_only"


def test_evidence_staleness_requires_reanalysis():
    result = evaluate_recommendation_currency(
        BASE_STORED,
        {"evidence_hash": "evidence-b", "analysis_result_id": "analysis-a", "policy_hash": "policy-a"},
    )

    assert result["recommendation_status"] == "stale"
    assert result["stale_reason"] == ["evidence"]
    assert result["minimum_refresh"] == "rebuild_evidence_pack_and_rerun_analysis"


def test_analysis_staleness_requires_analysis_and_action_refresh():
    result = evaluate_recommendation_currency(
        BASE_STORED,
        {"evidence_hash": "evidence-a", "analysis_result_id": "analysis-b", "policy_hash": "policy-a"},
    )

    assert result["recommendation_status"] == "stale"
    assert result["stale_reason"] == ["analysis"]
    assert result["minimum_refresh"] == "rerun_analysis_and_action_resolution"


def test_global_response_omits_local_fields_instead_of_nulling_them():
    response = build_global_response(
        format_label="PDF",
        analysed_band="Low",
        analysis_status="Assessed",
    )

    assert response == {
        "format": "PDF",
        "scope": "global",
        "analysed_band": "Low",
        "analysis_status": "Assessed",
    }
    assert not has_local_fields(response)
    assert "readiness_status" not in response
    assert "exposure_level" not in response
    assert "local_risk_posture" not in response
