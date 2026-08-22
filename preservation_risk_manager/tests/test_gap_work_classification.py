from __future__ import annotations

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.evidence_gaps import diagnose_format_evidence_gaps
from preservation_risk_manager.evidence_remediation import plan_format_evidence_remediation
from preservation_risk_manager.frameworks import RiskFramework


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "work_classification_test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": False,
            "min_completeness_for_band": 0.5,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 2},
                {"band": "Moderate", "min_score": 3, "max_score": 5},
                {"band": "High", "min_score": 6, "max_score": 8},
            ],
        },
        "questions": [
            {
                "id": "q_platform",
                "label": "Platform dependency?",
                "domain_id": "software_dependencies_environment",
                "evidence_fields": ["sustainability.platform_dependency"],
                "answers": [
                    {"id": "low", "points": 0},
                    {"id": "high", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
            {
                "id": "q_local",
                "label": "Local capability?",
                "domain_id": "local_institutional_feasibility",
                "evidence_fields": ["local.management_capability"],
                "answers": [
                    {"id": "low", "points": 0},
                    {"id": "high", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
            {
                "id": "q_image",
                "label": "Image fidelity?",
                "domain_id": "essential_characteristics",
                "applicability": ["image", "graphics"],
                "evidence_fields": ["fidelity.image"],
                "answers": [
                    {"id": "low", "points": 0},
                    {"id": "high", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
            {
                "id": "q_generic",
                "label": "Generic source evidence?",
                "evidence_fields": ["example.generic"],
                "answers": [
                    {"id": "low", "points": 0},
                    {"id": "high", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
        ],
    })


def _reader() -> RegistryReader:
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {"canonical_id": "fmt-demo", "preferred_name": "Demo Format", "current": True},
        ],
        "criterion_claims": [],
        "risk_assessment_claims": [
            {
                "claim_id": "risk-1",
                "canonical_id": "fmt-demo",
                "source_id": "nara_digital_preservation_framework",
                "scope_type": "exact_format",
                "current": True,
            },
        ],
        "source_relationship_claims": [
            {
                "claim_id": "rel-1",
                "canonical_id": "fmt-demo",
                "source_id": "wikidata_file_formats",
                "relationship": "explicit_wikidata_identifier_cross_reference",
                "current": True,
            },
        ],
    }))


def test_gap_diagnosis_classifies_work_without_promoting_context_to_answers():
    reader = _reader()
    format_doc = reader.get_canonical_format("fmt-demo")
    assert format_doc is not None

    diagnostic = diagnose_format_evidence_gaps(reader, _framework(), format_doc)
    gaps = {item["question_id"]: item for item in diagnostic["missing_questions"]}

    assert gaps["q_platform"]["work_type"] == "automated_evidence_research_required"
    assert gaps["q_local"]["work_type"] == "institution_evidence_required"
    assert gaps["q_image"]["work_type"] == "content_specific_assessment_required"
    assert gaps["q_image"]["applicability"] == ["image", "graphics"]
    assert gaps["q_generic"]["work_type"] == "source_evidence_required"

    context = diagnostic["non_scoring_registry_context"]
    assert context["external_risk_assessment_count"] == 1
    assert context["external_risk_sources"] == {"nara_digital_preservation_framework": 1}
    assert context["relationship_claim_count"] == 1
    assert context["relationship_sources"] == {"wikidata_file_formats": 1}
    assert context["scoring_effect"] == "context_only"
    assert diagnostic["criterion_claims_available"] == 0
    assert diagnostic["gap_count"] == 4


def test_remediation_routes_each_gap_without_registry_rewrite_action():
    reader = _reader()
    format_doc = reader.get_canonical_format("fmt-demo")
    assert format_doc is not None

    diagnostic = diagnose_format_evidence_gaps(reader, _framework(), format_doc)
    plan = plan_format_evidence_remediation(diagnostic)
    items = {item["question_id"]: item for item in plan["remediation_items"]}

    assert items["q_platform"]["action_type"] == "automated_evidence_research"
    assert items["q_local"]["action_type"] == "institution_evidence_needed"
    assert items["q_image"]["action_type"] == "content_specific_assessment_needed"
    assert items["q_generic"]["action_type"] == "source_evidence_needed"
    assert all("registry" not in str(item["action_type"]) for item in items.values())
    assert plan["non_scoring_registry_context"]["external_risk_assessment_count"] == 1
