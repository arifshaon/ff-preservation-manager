from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.registry_audit_diagnostics import (
    refine_registry_risk_evidence_diagnostics,
    render_registry_audit_diagnostics_markdown,
)


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "diagnostic-test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Disclosure",
                "critical": True,
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "limited_or_unclear_specification", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_adoption",
                "label": "Adoption",
                "evidence_fields": ["sustainability.adoption"],
                "answers": [
                    {"id": "widely_adopted", "points": 0},
                    {"id": "niche_or_declining", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_external_dependencies",
                "label": "Dependencies",
                "weight": 2,
                "evidence_fields": ["technical.hardware_dependency"],
                "answers": [
                    {"id": "no_special_dependency", "points": 0},
                    {"id": "specialist_dependency", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
        ],
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": True,
            "min_completeness_for_band": 0.6666666666666666,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 5},
                {"band": "Moderate", "min_score": 6, "max_score": 12},
                {"band": "High", "min_score": 13, "max_score": 30},
            ],
        },
    })


def _reader() -> RegistryReader:
    formats = [
        {
            "canonical_id": "puid-fmt-1",
            "preferred_name": "PUID Partial",
            "identifiers": {"puid": ["fmt/1"]},
        },
        {
            "canonical_id": "puid-fmt-2",
            "preferred_name": "PUID Conflict",
            "identifiers": {"puid": ["fmt/2"]},
        },
        {
            "canonical_id": "fmt-generic",
            "preferred_name": "Generic No Evidence",
            "identifiers": {},
        },
    ]
    claims = [
        {
            "canonical_id": "puid-fmt-1",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF1",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-1",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF1",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF2",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "sustainability.disclosure",
            "value": "proprietary_documented",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd2",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "sustainability.adoption",
            "value": "high",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd2",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-2",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF2",
            "current": True,
        },
    ]
    return RegistryReader(store=JsonRegistryStore({"canonical_formats": formats, "criterion_claims": claims}))


def test_puid_diagnostics_explain_coverage_and_conflicts():
    report = refine_registry_risk_evidence_diagnostics(
        {"conflicts": {"count": 1}},
        _reader(),
        _framework(),
        sample_limit=10,
    )

    puid = report["puid_diagnostics"]
    assert puid["formats"] == 2
    assert puid["band_eligible_formats"] == 2
    assert puid["coverage_by_answered_questions"] == {"2": 1, "3": 1}
    assert puid["question_coverage"]["q_adoption"]["missing_evidence"] == 1
    assert puid["gap_patterns"] == {"q_adoption": 1}
    assert puid["source_support"]["loc_fdd_xml"] == 1
    assert puid["source_support"]["nara_digital_preservation_framework"] == 2

    conflicts = report["conflict_diagnostics"]
    assert conflicts["total"] == 1
    assert conflicts["puid_format_conflicts"] == 1
    assert conflicts["non_puid_format_conflicts"] == 0
    assert conflicts["matches_base_audit_count"] is True
    assert conflicts["by_question"] == {"q_disclosure": 1}
    assert conflicts["by_source_combination"] == {
        "loc_fdd_xml + nara_digital_preservation_framework": 1
    }
    assert conflicts["by_answer_combination"] == {
        "limited_or_unclear_specification vs public_specification": 1
    }


def test_diagnostic_markdown_contains_puid_and_conflict_sections():
    report = refine_registry_risk_evidence_diagnostics(
        {"conflicts": {"count": 1}},
        _reader(),
        _framework(),
        sample_limit=10,
    )
    markdown = render_registry_audit_diagnostics_markdown(report)

    assert "PUID production-path diagnostics" in markdown
    assert "PUID band suppression reasons" in markdown
    assert "Most common PUID gap patterns" in markdown
    assert "Conflict diagnostics" in markdown
    assert "loc_fdd_xml + nara_digital_preservation_framework" in markdown
