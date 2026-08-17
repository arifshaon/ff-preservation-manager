from pathlib import Path

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework, load_framework
from preservation_risk_manager.request_api import execute_request


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "question_test",
        "version": "1.0",
        "calibration_status": "draft_unvalidated",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": False,
            "min_completeness_for_band": 0.5,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 1},
                {"band": "Moderate", "min_score": 2, "max_score": 3},
                {"band": "High", "min_score": 4, "max_score": 10},
            ],
        },
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Is the specification public?",
                "domain_id": "specification_governance",
                "domain_label": "Specification Disclosure & Governance",
                "definition": "Specification availability.",
                "guidance": "Use normative specification evidence.",
                "aliases": ["public specification"],
                "critical": True,
                "evidence_fields": ["sustainability.disclosure"],
                "evidence_value_map": {
                    "public_specification": "low_risk",
                    "restricted": "high_risk",
                },
                "answers": [
                    {"id": "low_risk", "label": "Public", "points": 0},
                    {"id": "high_risk", "label": "Restricted", "points": 2},
                    {"id": "unknown", "label": "Unknown", "points": 0, "abstention": True},
                ],
            },
            {
                "id": "q_external_assets",
                "label": "External assets?",
                "domain_id": "software_dependencies_environment",
                "domain_label": "Software Dependencies & Environment",
                "applicability": ["all"],
                "evidence_fields": ["sustainability.external_dependencies"],
                "evidence_value_map": {"none": "low_risk", "high": "high_risk"},
                "answers": [
                    {"id": "low_risk", "label": "None", "points": 0},
                    {"id": "high_risk", "label": "Required", "points": 2},
                    {"id": "unknown", "label": "Unknown", "points": 0, "abstention": True},
                ],
            },
        ],
    })


def _reader() -> RegistryReader:
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {"canonical_id": "fmt-pdf", "preferred_name": "PDF", "current": True},
        ],
        "criterion_claims": [
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "loc",
            },
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.external_dependencies",
                "value": "none",
                "source_id": "loc",
            },
        ],
    }))


def test_list_assessment_questions_can_filter_domain():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "list_assessment_questions",
            "filters": {"domains": ["software_dependencies_environment"]},
            "scope": "global",
        },
    )

    assert result["status"] == "ok"
    assert result["framework"]["calibration_status"] == "draft_unvalidated"
    assert result["framework"]["banding_enabled"] is False
    assert result["result_count"] == 1
    assert result["results"][0]["question_id"] == "q_external_assets"
    assert result["results"][0]["domain_id"] == "software_dependencies_environment"


def test_targeted_question_assessment_uses_question_local_mapping_without_emitting_band():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "assess_format_questions",
            "format": "PDF",
            "filters": {"domains": ["specification_governance"]},
            "scope": "global",
        },
    )

    assert result["status"] == "ok"
    assessment = result["result"]
    assert assessment["selected_question_count"] == 1
    assert assessment["answered_question_count"] == 1
    row = assessment["questions"][0]
    assert row["question_id"] == "q_disclosure"
    assert row["answer_id"] == "low_risk"
    assert row["derivation_status"] == "derived"
    assert row["matched_evidence_count"] == 1
    assert assessment["overall_framework_assessment"]["risk_band"] is None
    assert assessment["overall_framework_assessment"]["band_suppressed_reason"] == "framework_not_calibrated"


def test_comprehensive_qnl_draft_framework_has_eight_domains_and_22_questions():
    path = Path(__file__).parents[1] / "examples" / "qnl_preservation_risk_questions.framework.draft.json"
    framework = load_framework(path)

    assert framework.framework_id == "qnl_preservation_risk_questions"
    assert framework.calibration_status == "draft_unvalidated"
    assert framework.banding_enabled is False
    assert len(framework.questions) == 22
    assert len({question.domain_id for question in framework.questions}) == 8
    assert framework.question_by_id("q_image_fidelity").applicability == ("image", "graphics")
    assert framework.question_by_id("q_external_assets").mapped_answer_id("none") == "low_risk"
