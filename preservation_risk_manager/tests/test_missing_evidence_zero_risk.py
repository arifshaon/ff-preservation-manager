from __future__ import annotations

from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "missing_evidence_zero_risk",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.0,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 2},
                {"band": "Moderate", "min_score": 3, "max_score": 5},
                {"band": "High", "min_score": 6, "max_score": 20},
            ],
        },
        "questions": [
            {
                "id": "q_known",
                "label": "Known evidence",
                "answers": [
                    {"id": "moderate", "points": 3},
                    {"id": "unknown", "points": 5, "abstention": True},
                ],
            },
            {
                "id": "q_missing",
                "label": "Missing evidence",
                "answers": [
                    {"id": "high", "points": 8},
                    {"id": "unknown", "points": 5, "abstention": True},
                ],
            },
        ],
    })


def test_missing_question_is_visible_but_contributes_zero_risk_points():
    result = score_answers(_framework(), {"q_known": "moderate"})

    assert result["score"] == 3
    assert result["answered_questions"] == 1
    assert result["missing_count"] == 1
    missing = next(row for row in result["question_results"] if row["question_id"] == "q_missing")
    assert missing["answer_id"] == "unknown"
    assert missing["abstention"] is True
    assert missing["missing"] is True
    assert missing["points"] == 0
    assert missing["weighted_points"] == 0


def test_explicit_unknown_abstention_also_contributes_zero_risk_points():
    result = score_answers(
        _framework(),
        {
            "q_known": "moderate",
            "q_missing": "unknown",
        },
    )

    assert result["score"] == 3
    unknown = next(row for row in result["question_results"] if row["question_id"] == "q_missing")
    assert unknown["abstention"] is True
    assert unknown["points"] == 0
    assert unknown["weighted_points"] == 0
