from __future__ import annotations

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.evidence_gaps import diagnose_format_evidence_gaps
from preservation_risk_manager.evidence_remediation import plan_format_evidence_remediation
from preservation_risk_manager.frameworks import RiskFramework


def _framework() -> RiskFramework:
    def question(question_id, domain_id, field, *, applicability=None):
        return {
            "id": question_id,
            "label": question_id,
            "domain_id": domain_id,
            "evidence_fields": [field],
            "applicability": applicability or [],
            "answers": [
                {"id": "low", "points": 0},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
            "evidence_value_map": {"known": "low"},
        }

    return RiskFramework.from_dict({
        "framework_id": "request_applicability",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.5,
            "banding_enabled": False,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 1},
                {"band": "Moderate", "min_score": 2, "max_score": 3},
                {"band": "High", "min_score": 4, "max_score": 10},
            ],
        },
        "questions": [
            question("q_answered", "specification_governance", "global.answered"),
            question("q_global_gap", "specification_governance", "global.missing"),
            question("q_local", "local_institutional_feasibility", "local.capability"),
            question("q_image", "essential_characteristics", "fidelity.image", applicability=["image"]),
            question("q_av", "essential_characteristics", "fidelity.av", applicability=["audio", "video"]),
        ],
    })


def _reader() -> RegistryReader:
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {"canonical_id": "fmt-x", "preferred_name": "Format X", "current": True},
        ],
        "criterion_claims": [
            {
                "canonical_id": "fmt-x",
                "criterion_id": "global.answered",
                "value": "known",
                "source_id": "test",
                "review_status": "approved",
                "current": True,
            },
        ],
    }))


def test_global_gap_diagnosis_separates_actionable_and_deferred_questions():
    diagnostic = diagnose_format_evidence_gaps(
        _reader(),
        _framework(),
        {"canonical_id": "fmt-x", "preferred_name": "Format X", "current": True},
    )

    assert diagnostic["evidence_completeness"] == 0.2
    assert diagnostic["applicable_question_count"] == 2
    assert diagnostic["applicable_answered_question_count"] == 1
    assert diagnostic["applicable_evidence_completeness"] == 0.5
    assert diagnostic["gap_count"] == 1
    assert diagnostic["total_unresolved_question_count"] == 4
    assert diagnostic["deferred_question_count"] == 3
    assert diagnostic["deferred_reason_counts"] == {
        "deferred_until_content_type": 2,
        "deferred_until_institution_scope": 1,
    }
    assert [row["question_id"] for row in diagnostic["missing_questions"]] == ["q_global_gap"]

    plan = plan_format_evidence_remediation(diagnostic)
    assert plan["remediation_item_count"] == 1
    assert plan["deferred_question_count"] == 3
    assert plan["remediation_items"][0]["question_id"] == "q_global_gap"


def test_content_type_makes_matching_fidelity_question_applicable_and_excludes_other_fidelity():
    diagnostic = diagnose_format_evidence_gaps(
        _reader(),
        _framework(),
        {"canonical_id": "fmt-x", "preferred_name": "Format X", "current": True},
        content_type="image",
    )

    assert diagnostic["applicable_question_count"] == 3
    assert diagnostic["gap_count"] == 2
    assert diagnostic["deferred_question_count"] == 1
    assert diagnostic["excluded_question_count"] == 1
    assert {row["question_id"] for row in diagnostic["missing_questions"]} == {"q_global_gap", "q_image"}
    assert diagnostic["deferred_questions"][0]["question_id"] == "q_local"
    assert diagnostic["excluded_questions"][0]["question_id"] == "q_av"


def test_institution_scope_activates_local_question():
    diagnostic = diagnose_format_evidence_gaps(
        _reader(),
        _framework(),
        {"canonical_id": "fmt-x", "preferred_name": "Format X", "current": True},
        institution_id="qnl",
    )

    assert diagnostic["applicable_question_count"] == 3
    assert diagnostic["gap_count"] == 2
    assert diagnostic["deferred_question_count"] == 2
    assert {row["question_id"] for row in diagnostic["missing_questions"]} == {"q_global_gap", "q_local"}
