from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.frameworks import RiskFramework


def test_undocumented_registry_disclosure_is_not_treated_as_unknown():
    framework = RiskFramework.from_dict({
        "framework_id": "disclosure-test",
        "version": "1",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 1.0,
            "bands": [{"band": "Low", "min_score": 0, "max_score": 10}],
        },
        "questions": [{
            "id": "q_disclosure",
            "evidence_fields": ["sustainability.disclosure"],
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_or_unclear_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        }],
    })

    result = derive_answers(
        framework,
        {"global_evidence": [{"criterion_id": "sustainability.disclosure", "value": "undocumented"}]},
    )

    assert result["answers"]["q_disclosure"] == "limited_or_unclear_specification"
    assert result["derivation"]["q_disclosure"]["status"] == "derived"
    assert result["scoring_answers"]["q_disclosure"]["missing"] is False
