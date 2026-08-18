from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.registry_audit_conflict_classification import refine_conflict_semantics


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "conflict-classification-test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "questions": [
            {
                "id": "q_external_dependencies",
                "label": "Dependencies",
                "evidence_fields": [
                    "technical.hardware_dependency",
                    "technical.plugin_script_dependency",
                ],
                "answers": [
                    {"id": "no_special_dependency", "points": 0},
                    {"id": "specialist_dependency", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            }
        ],
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": True,
            "min_completeness_for_band": 1.0,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 3},
                {"band": "High", "min_score": 4, "max_score": 10},
            ],
        },
    })


def _reader() -> RegistryReader:
    formats = [
        {
            "canonical_id": "puid-fmt-1",
            "preferred_name": "Composite Format",
            "identifiers": {"puid": ["fmt/1"]},
        },
        {
            "canonical_id": "puid-fmt-2",
            "preferred_name": "Genuine Conflict Format",
            "identifiers": {"puid": ["fmt/2"]},
        },
    ]
    claims = [
        {
            "canonical_id": "puid-fmt-1",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara",
            "source_record_id": "NF1",
            "mapping_rule_id": "nara.5_1",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-1",
            "criterion_id": "technical.plugin_script_dependency",
            "value": "high",
            "source_id": "nara",
            "source_record_id": "NF1",
            "mapping_rule_id": "nara.6_3",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara",
            "source_record_id": "NF2",
            "mapping_rule_id": "nara.5_1",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "technical.hardware_dependency",
            "value": "high",
            "source_id": "nara",
            "source_record_id": "NF2",
            "mapping_rule_id": "nara.5_2",
            "current": True,
        },
    ]
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": formats,
        "criterion_claims": claims,
    }))


def test_conflict_classification_separates_composite_from_same_criterion_disagreement():
    report = {"summary": {}, "conflicts": {"count": 2}}

    refined = refine_conflict_semantics(report, _reader(), _framework(), sample_limit=10)
    interpretation = refined["conflict_interpretation"]

    assert interpretation["raw_derived_conflict_count"] == 2
    assert interpretation["genuine_evidence_conflicts"] == 1
    assert interpretation["composite_aggregations"] == 1
    assert interpretation["unclassified_conflicts"] == 0
    assert interpretation["puid_genuine_evidence_conflicts"] == 1
    assert interpretation["puid_composite_aggregations"] == 1
    assert interpretation["genuine_by_evidence_field"] == {"technical.hardware_dependency": 1}
    assert interpretation["composite_by_question"] == {"q_external_dependencies": 1}
    assert refined["summary"]["raw_derived_conflict_format_questions"] == 2
    assert refined["summary"]["genuine_evidence_conflict_format_questions"] == 1
    assert refined["summary"]["composite_aggregation_format_questions"] == 1


def test_composite_sample_exposes_component_answers_without_changing_scoring():
    report = {"summary": {}, "conflicts": {"count": 2}}

    refined = refine_conflict_semantics(report, _reader(), _framework(), sample_limit=10)
    sample = refined["conflict_interpretation"]["composite_samples"][0]

    assert sample["canonical_id"] == "puid-fmt-1"
    assert sample["field_answers"] == {
        "technical.hardware_dependency": ["no_special_dependency"],
        "technical.plugin_script_dependency": ["specialist_dependency"],
    }
    assert sample["conflicting_answer_ids"] == [
        "no_special_dependency",
        "specialist_dependency",
    ]
