from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.registry_audit_governance import refine_registry_risk_evidence_audit


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "audit-governance-test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Disclosure",
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            }
        ],
        "scale": {
            "direction": "higher_is_risk",
            "banding_enabled": True,
            "min_completeness_for_band": 1.0,
            "bands": [{"band": "Low", "min_score": 0, "max_score": 5}],
        },
    })


def test_refinement_separates_total_and_global_scope_claim_counts():
    reader = RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [],
        "criterion_claims": [
            {
                "canonical_id": "puid-fmt-1",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "global-source",
                "current": True,
            },
            {
                "canonical_id": "fmt-local",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "qnl-source",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-old",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "old-source",
                "current": False,
            },
        ],
    }))
    report = {
        "summary": {"current_criterion_claims": 999},
        "draft_mapping_opportunities": {"status": "not_requested"},
    }

    refined = refine_registry_risk_evidence_audit(report, reader, _framework())

    assert refined["summary"]["current_criterion_claims"] == 1
    assert refined["summary"]["current_criterion_claims_in_scope"] == 1
    assert refined["summary"]["current_criterion_claims_total"] == 2
    assert refined["summary"]["institution_scoped_current_claims_total"] == 1
    assert "Global audits exclude institution-scoped" in refined["summary"]["claim_scope_note"]


def test_refinement_institution_scope_includes_global_and_matching_local_claims():
    reader = RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [],
        "criterion_claims": [
            {
                "canonical_id": "puid-fmt-1",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "global-source",
                "current": True,
            },
            {
                "canonical_id": "fmt-qnl",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "qnl-source",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "current": True,
            },
            {
                "canonical_id": "fmt-other",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "other-source",
                "institution_id": "other",
                "source_independence": "institution_scoped",
                "current": True,
            },
        ],
    }))
    report = {
        "summary": {},
        "draft_mapping_opportunities": {"status": "not_requested"},
    }

    refined = refine_registry_risk_evidence_audit(
        report,
        reader,
        _framework(),
        institution_id="qnl",
    )

    assert refined["summary"]["current_criterion_claims_in_scope"] == 2
    assert refined["summary"]["current_criterion_claims_total"] == 3
    assert refined["summary"]["institution_scoped_current_claims_total"] == 2
