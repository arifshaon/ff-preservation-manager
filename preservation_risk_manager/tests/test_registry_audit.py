from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.registry_audit import (
    _questions_by_criterion,
    build_registry_risk_evidence_audit,
    render_registry_risk_evidence_audit_markdown,
)


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "audit-test",
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
            "canonical_id": "puid-fmt-14",
            "preferred_name": "PDF 1.0",
            "identifiers": {"puid": ["fmt/14"]},
            "source_records": [
                {
                    "source_id": "loc_fdd_xml",
                    "source_record_id": "fdd000316",
                    "relationship": "explicit_puid_cross_reference",
                    "evidence_scope": "multi_puid_source_record",
                }
            ],
        },
        {
            "canonical_id": "puid-fmt-99",
            "preferred_name": "Conflict Format",
            "identifiers": {"puid": ["fmt/99"]},
        },
        {
            "canonical_id": "puid-fmt-100",
            "preferred_name": "No Evidence Format",
            "identifiers": {"puid": ["fmt/100"]},
        },
    ]
    claims = [
        {
            "canonical_id": "puid-fmt-14",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF00362",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-14",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF00362",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-99",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF00099",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-99",
            "criterion_id": "sustainability.disclosure",
            "value": "proprietary_documented",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd000099",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-99",
            "criterion_id": "sustainability.adoption",
            "value": "high",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd000099",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-99",
            "criterion_id": "technical.hardware_dependency",
            "value": "none",
            "source_id": "nara_digital_preservation_framework",
            "source_record_id": "NF00099",
            "current": True,
        },
        {
            "canonical_id": "puid-fmt-99",
            "criterion_id": "sustainability.adoption",
            "value": "low",
            "source_id": "old_source",
            "source_record_id": "old",
            "current": False,
        },
    ]
    return RegistryReader(store=JsonRegistryStore({"canonical_formats": formats, "criterion_claims": claims}))


def test_registry_audit_reports_coverage_bands_conflicts_and_sources():
    report = build_registry_risk_evidence_audit(_reader(), _framework(), sample_limit=10)

    assert report["summary"]["canonical_formats"] == 3
    assert report["summary"]["current_criterion_claims"] == 6
    assert report["summary"]["band_eligible_formats"] == 2
    assert report["summary"]["puid_band_eligible_formats"] == 2
    assert report["coverage_by_answered_questions"] == {"0": 1, "2": 1, "3": 1}
    assert report["band_distribution"] == {"Low": 2}
    assert report["conflicts"]["count"] == 1
    assert report["conflicts"]["samples"][0]["canonical_id"] == "puid-fmt-99"
    assert report["question_coverage"]["q_adoption"]["missing_evidence"] == 2
    assert report["source_contribution"]["loc_fdd_xml"]["claims"] == 2
    assert report["criterion_coverage"]["sustainability.disclosure"]["formats_with_claim"] == 2
    assert report["loc_relationship_scopes"] == {"multi_puid_source_record": 1}
    assert report["draft_mapping_opportunities"]["status"] == "not_requested"


def test_registry_audit_markdown_contains_decision_sections():
    report = build_registry_risk_evidence_audit(_reader(), _framework(), sample_limit=10)
    markdown = render_registry_risk_evidence_audit_markdown(report)

    assert "Registry-wide Preservation Risk / Evidence Audit" in markdown
    assert "Question coverage" in markdown
    assert "Evidence contribution by source" in markdown
    assert "Draft mapping opportunities" in markdown
    assert "puid-fmt-99" in markdown


def test_audit_question_index_honors_governed_evidence_field_compatibility():
    framework = RiskFramework.from_dict({
        "framework_id": "compatibility-audit-test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "questions": [
            {
                "id": "q_ip_constraints",
                "evidence_fields": ["rights.ip_constraints"],
                "answers": [
                    {"id": "low_risk", "points": 0},
                    {"id": "high_risk", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
            {
                "id": "q_tpm_drm",
                "evidence_fields": ["rights.tpm_drm_encryption"],
                "answers": [
                    {"id": "low_risk", "points": 0},
                    {"id": "high_risk", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            },
        ],
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": False,
            "min_completeness_for_band": 1.0,
            "bands": [{"band": "Low", "min_score": 0, "max_score": 4}],
        },
    })

    indexed = _questions_by_criterion(framework)

    assert indexed["rights.ip_constraints"] == ["q_ip_constraints"]
    assert indexed["sustainability.ip_licensing"] == ["q_ip_constraints"]
    assert indexed["rights.tpm_drm_encryption"] == ["q_tpm_drm"]
    assert indexed["sustainability.tpm_encryption"] == ["q_tpm_drm"]
