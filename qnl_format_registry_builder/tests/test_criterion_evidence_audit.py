from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_evidence_audit import run_criterion_evidence_audit
from registry_builder.storage.memory import MemoryRegistryStore


CRITERIA = CriteriaVocabulary({
    "criteria_version": "v1",
    "criteria": {
        "sustainability.disclosure": {
            "kind": "ordinal",
            "values": ["public_specification", "partial_specification"],
            "null_value": "unknown",
        }
    },
})


MAPPING = {
    "source_type": "qnl_institution_format_evidence",
    "mapping_version": "2026-08-15",
    "criteria_version": "v1",
    "decided_by": "QNL",
    "excluded_from_criteria": [{"field": "risk_direction", "reason": "not a value"}],
    "maps": [
        {
            "id": "qnl.disclosure.v1",
            "criterion": "sustainability.disclosure",
            "from_collection": "institution_evidence_claims",
            "from_field": "evidence_value",
            "where": {"criterion_id": "sustainability.disclosure"},
            "directness": "explicit",
            "covers": "partial",
            "source_independence": "institution_scoped",
            "mapping_status": "accepted",
            "values": {"publicly_documented": "public_specification"},
        }
    ],
}


def test_criterion_evidence_audit_reports_inventory_and_projected_coverage(tmp_path):
    store = MemoryRegistryStore()
    store.save_source_record({
        "source_id": "qnl_seed",
        "source_type": "qnl_institution_format_evidence",
        "source_record_id": "qnl-pdf",
        "raw": {"format": "PDF"},
    })
    store.upsert_canonical_format({
        "canonical_id": "fmt-pdf",
        "preferred_name": "PDF",
        "current": True,
        "source_records": [
            {
                "source_id": "qnl_seed",
                "source_type": "qnl_institution_format_evidence",
                "source_record_id": "qnl-pdf",
            }
        ],
        "institution_evidence_claims": [
            {
                "claim_id": "claim-1",
                "institution_id": "qnl",
                "criterion_id": "sustainability.disclosure",
                "evidence_value": "publicly_documented",
            }
        ],
    })
    mappings_dir = tmp_path / "mappings"
    mappings_dir.mkdir()
    mapping_path = mappings_dir / "qnl.json"
    mapping_path.write_text(__import__("json").dumps(MAPPING), encoding="utf-8")

    report = run_criterion_evidence_audit(store, criteria=CRITERIA, mappings_path=mappings_dir)

    assert report["status"] == "ok"
    assert report["canonical_formats"] == 1
    assert report["qnl_institution_evidence"]["institution_evidence_claims"] == 1
    assert report["excluded_fields"]["qnl_institution_format_evidence"][0]["field"] == "risk_direction"
    assert report["accepted_mapping_coverage"]["sustainability.disclosure"]["formats_with_any_claim"] == 1
