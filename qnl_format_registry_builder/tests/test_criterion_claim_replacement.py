from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_mapping import backfill_criterion_claims
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
    "native_vocabulary": "qnl_seed",
    "claim_review_status": "approved",
    "decided_by": "QNL DCPA",
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


def test_replace_source_claims_supersedes_old_current_claims_from_same_source():
    store = MemoryRegistryStore()
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
    store.save_criterion_claim({
        "canonical_id": "fmt-pdf",
        "criterion_id": "sustainability.disclosure",
        "value": "partial_specification",
        "source_id": "qnl_seed",
        "source_type": "qnl_institution_format_evidence",
        "source_record_id": "qnl-pdf",
        "mapping_rule_id": "qnl.old_disclosure.v1",
        "institution_id": "qnl",
        "current": True,
    })

    result = backfill_criterion_claims(
        store=store,
        criteria=CRITERIA,
        mappings=[MAPPING],
        replace_source_claims=True,
    )

    assert result["claims_generated"] == 1
    assert result["claims_superseded"] == 1
    claims = store.query("criterion_claims")
    old_claim = next(claim for claim in claims if claim["mapping_rule_id"] == "qnl.old_disclosure.v1")
    new_claim = next(claim for claim in claims if claim["mapping_rule_id"] == "qnl.disclosure.v1")
    assert old_claim["current"] is False
    assert old_claim["superseded_reason"] == "source_replaced_by_backfill"
    assert new_claim["current"] is True
    assert new_claim["value"] == "public_specification"
