from __future__ import annotations

import json

import pytest

from preservation_risk_manager.errors import FrameworkError
from preservation_risk_manager.frameworks import RiskFramework, load_framework


VALID_FRAMEWORK = {
    "framework_id": "qnl_sustainability_fixture",
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
            "label": "Is the format publicly documented?",
            "critical": True,
            "evidence_fields": ["sustainability.disclosure"],
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_adoption",
            "label": "Is the format widely adopted?",
            "answers": [
                {"id": "widely_adopted", "points": 0},
                {"id": "niche_or_declining", "points": 4},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
    ],
}


def test_framework_loader_accepts_valid_framework_dict():
    framework = RiskFramework.from_dict(VALID_FRAMEWORK)

    assert framework.framework_id == "qnl_sustainability_fixture"
    assert framework.version == "0.1.0"
    assert framework.max_score == 7
    assert framework.question_by_id("q_disclosure").critical is True
    assert framework.band_for_score(5) == "Moderate"


def test_load_framework_reads_json_file(tmp_path):
    path = tmp_path / "framework.json"
    path.write_text(json.dumps(VALID_FRAMEWORK), encoding="utf-8")

    framework = load_framework(path)

    assert framework.framework_id == "qnl_sustainability_fixture"
    assert [question.id for question in framework.questions] == ["q_disclosure", "q_adoption"]


def test_framework_rejects_duplicate_question_ids():
    data = dict(VALID_FRAMEWORK)
    data["questions"] = [VALID_FRAMEWORK["questions"][0], VALID_FRAMEWORK["questions"][0]]

    with pytest.raises(FrameworkError, match="duplicate question IDs"):
        RiskFramework.from_dict(data)


def test_framework_rejects_duplicate_answer_ids():
    data = json.loads(json.dumps(VALID_FRAMEWORK))
    data["questions"][0]["answers"] = [
        {"id": "same", "points": 0},
        {"id": "same", "points": 2},
    ]

    with pytest.raises(FrameworkError, match="duplicate answer IDs"):
        RiskFramework.from_dict(data)


def test_framework_rejects_overlapping_score_bands():
    data = json.loads(json.dumps(VALID_FRAMEWORK))
    data["score_bands"] = [
        {"band": "Low", "min_score": 0, "max_score": 5},
        {"band": "Moderate", "min_score": 5, "max_score": 10},
    ]

    with pytest.raises(FrameworkError, match="overlaps"):
        RiskFramework.from_dict(data)


def test_framework_rejects_undeclared_answer_id():
    framework = RiskFramework.from_dict(VALID_FRAMEWORK)

    with pytest.raises(FrameworkError, match="does not allow answer ID"):
        framework.question_by_id("q_disclosure").answer_by_id("made_up_answer")
