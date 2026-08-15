from __future__ import annotations

import pytest

from preservation_risk_manager.errors import FrameworkError
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


FRAMEWORK_DATA = {
    "framework_id": "qnl_scoring_fixture",
    "version": "0.1.0",
    "unknown_answer_id": "unknown",
    "score_bands": [
        {"band": "Low", "min_score": 0, "max_score": 3},
        {"band": "Moderate", "min_score": 4, "max_score": 7},
        {"band": "High", "min_score": 8, "max_score": 20},
    ],
    "questions": [
        {
            "id": "q_disclosure",
            "critical": True,
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_adoption",
            "answers": [
                {"id": "widely_adopted", "points": 0},
                {"id": "niche_or_declining", "points": 4},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_external_dependencies",
            "weight": 2,
            "answers": [
                {"id": "no_special_dependency", "points": 0},
                {"id": "specialist_dependency", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
    ],
}


def _framework() -> RiskFramework:
    return RiskFramework.from_dict(FRAMEWORK_DATA)


def test_scoring_computes_score_band_and_completeness_for_assessed_format():
    result = score_answers(
        _framework(),
        {
            "q_disclosure": "public_specification",
            "q_adoption": "niche_or_declining",
            "q_external_dependencies": "no_special_dependency",
        },
    )

    assert result["score"] == 4
    assert result["max_score"] == 13
    assert result["analysed_band"] == "Moderate"
    assert result["analysis_status"] == "Assessed"
    assert result["answered_questions"] == 3
    assert result["abstention_count"] == 0
    assert result["critical_abstention_count"] == 0
    assert result["evidence_completeness"] == 1.0


def test_scoring_uses_question_weight_for_points():
    result = score_answers(
        _framework(),
        {
            "q_disclosure": "limited_specification",
            "q_adoption": "niche_or_declining",
            "q_external_dependencies": "specialist_dependency",
        },
    )

    assert result["score"] == 13
    assert result["analysed_band"] == "High"
    external = next(row for row in result["question_results"] if row["question_id"] == "q_external_dependencies")
    assert external["points"] == 3
    assert external["weight"] == 2
    assert external["weighted_points"] == 6


def test_missing_noncritical_answer_becomes_partial_assessment_abstention():
    result = score_answers(
        _framework(),
        {
            "q_disclosure": "public_specification",
            "q_external_dependencies": "no_special_dependency",
        },
    )

    assert result["analysis_status"] == "Partially Assessed"
    assert result["analysed_band"] == "Low"
    assert result["answered_questions"] == 2
    assert result["missing_count"] == 1
    assert result["abstention_count"] == 1
    assert result["critical_abstention_count"] == 0
    assert result["evidence_completeness"] == pytest.approx(2 / 3)
    adoption = next(row for row in result["question_results"] if row["question_id"] == "q_adoption")
    assert adoption["answer_id"] == "unknown"
    assert adoption["abstention"] is True
    assert adoption["missing"] is True


def test_critical_abstention_blocks_band_and_requires_assessment():
    result = score_answers(
        _framework(),
        {
            "q_disclosure": "unknown",
            "q_adoption": "widely_adopted",
            "q_external_dependencies": "no_special_dependency",
        },
    )

    assert result["analysis_status"] == "Needs Assessment"
    assert result["analysed_band"] is None
    assert result["critical_abstention_count"] == 1
    assert result["evidence_completeness"] == pytest.approx(2 / 3)


def test_all_missing_answers_are_not_assessed():
    result = score_answers(_framework(), {})

    assert result["analysis_status"] == "Not Assessed"
    assert result["analysed_band"] is None
    assert result["answered_questions"] == 0
    assert result["abstention_count"] == 3
    assert result["critical_abstention_count"] == 1
    assert result["evidence_completeness"] == 0


def test_scoring_rejects_answer_ids_not_allowed_by_framework():
    with pytest.raises(FrameworkError, match="does not allow answer ID"):
        score_answers(_framework(), {"q_disclosure": "invented_answer"})
