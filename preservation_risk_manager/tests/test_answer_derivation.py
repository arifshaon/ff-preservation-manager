from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.frameworks import RiskFramework


def _framework():
    return RiskFramework.from_dict({
        "framework_id": "example",
        "version": "1",
        "score_bands": [{"band": "Low", "min_score": 0, "max_score": 10}],
        "questions": [
            {
                "id": "q_disclosure",
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "limited_or_unclear_specification", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_external_dependencies",
                "evidence_fields": ["sustainability.external_dependencies"],
                "answers": [
                    {"id": "no_special_dependency", "points": 0},
                    {"id": "specialist_dependency", "points": 5},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
        ],
    })


def test_derives_answers_from_explicit_criterion_evidence():
    evidence_pack = {
        "global_evidence": [
            {"claim_id": "a", "criterion_id": "sustainability.disclosure", "value": "openly_documented"},
            {"claim_id": "b", "criterion_id": "sustainability.external_dependencies", "value": "none"},
        ]
    }

    derived = derive_answers(_framework(), evidence_pack)

    assert derived["answers"] == {
        "q_disclosure": "public_specification",
        "q_external_dependencies": "no_special_dependency",
    }
    assert derived["derivation"]["q_disclosure"]["status"] == "derived"


def test_missing_evidence_remains_unknown_not_inferred():
    derived = derive_answers(_framework(), {"global_evidence": []})

    assert derived["answers"]["q_disclosure"] == "unknown"
    assert derived["derivation"]["q_disclosure"]["status"] == "missing_evidence"


def test_conflicting_evidence_uses_highest_risk_answer_and_exposes_conflict():
    evidence_pack = {
        "global_evidence": [
            {"claim_id": "a", "criterion_id": "sustainability.external_dependencies", "value": "none"},
            {"claim_id": "b", "criterion_id": "sustainability.external_dependencies", "value": "specialist_dependency"},
        ]
    }

    derived = derive_answers(_framework(), evidence_pack)

    assert derived["answers"]["q_external_dependencies"] == "specialist_dependency"
    details = derived["derivation"]["q_external_dependencies"]
    assert details["status"] == "derived_conflict_conservative"
    assert details["conflicting_answer_ids"] == ["no_special_dependency", "specialist_dependency"]
