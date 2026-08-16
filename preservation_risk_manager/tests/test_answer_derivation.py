from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.frameworks import RiskFramework


def _framework():
    return RiskFramework.from_dict({
        "framework_id": "example",
        "version": "1",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.5,
            "bands": [{"band": "Low", "min_score": 0, "max_score": 10}],
        },
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
                "id": "q_adoption",
                "evidence_fields": ["sustainability.adoption"],
                "answers": [
                    {"id": "widely_adopted", "points": 0},
                    {"id": "niche_or_declining", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_external_dependencies",
                "evidence_fields": ["sustainability.external_dependencies", "technical.container_complexity"],
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
        "q_adoption": "unknown",
        "q_external_dependencies": "no_special_dependency",
    }
    assert derived["scoring_answers"]["q_disclosure"] == {
        "answer_id": "public_specification",
        "derivation_status": "derived",
        "missing": False,
    }
    assert derived["derivation"]["q_disclosure"]["status"] == "derived"


def test_missing_evidence_remains_unknown_not_inferred():
    derived = derive_answers(_framework(), {"global_evidence": []})

    assert derived["answers"]["q_disclosure"] == "unknown"
    assert derived["scoring_answers"]["q_disclosure"] == {
        "answer_id": "unknown",
        "derivation_status": "missing_evidence",
        "missing": True,
    }
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
    assert derived["scoring_answers"]["q_external_dependencies"] == {
        "answer_id": "specialist_dependency",
        "derivation_status": "derived_conflict_conservative",
        "missing": False,
    }
    details = derived["derivation"]["q_external_dependencies"]
    assert details["status"] == "derived_conflict_conservative"
    assert details["conflicting_answer_ids"] == ["no_special_dependency", "specialist_dependency"]


def test_derives_answers_from_registry_criterion_claim_values():
    evidence_pack = {
        "global_evidence": [
            {"criterion_id": "sustainability.disclosure", "value": "partial_specification"},
            {"criterion_id": "sustainability.adoption", "value": "high"},
            {"criterion_id": "sustainability.external_dependencies", "value": "low"},
            {"criterion_id": "technical.container_complexity", "value": "wrapper"},
        ]
    }

    derived = derive_answers(_framework(), evidence_pack)

    assert derived["answers"] == {
        "q_disclosure": "limited_or_unclear_specification",
        "q_adoption": "widely_adopted",
        "q_external_dependencies": "no_special_dependency",
    }


def test_institution_evidence_participates_in_answer_derivation():
    evidence_pack = {
        "scope": "institution",
        "institution_id": "qnl",
        "global_evidence": [],
        "institution_evidence": [
            {"criterion_id": "sustainability.adoption", "value": "low", "institution_id": "qnl"},
            {"criterion_id": "sustainability.external_dependencies", "value": "high", "institution_id": "qnl"},
        ],
    }

    derived = derive_answers(_framework(), evidence_pack)

    assert derived["answers"]["q_adoption"] == "niche_or_declining"
    assert derived["answers"]["q_external_dependencies"] == "specialist_dependency"
