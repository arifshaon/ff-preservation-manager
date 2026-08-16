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


def test_backfill_result_reports_counts_by_mapping_rule():
    store = MemoryRegistryStore()
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-18",
        "current": True,
        "source_records": [
            {
                "source_id": "pronom_registry",
                "source_type": "pronom_registry",
                "source_record_id": "fmt/18",
            }
        ],
    })
    store.save_source_record({
        "source_id": "pronom_registry",
        "source_type": "pronom_registry",
        "source_record_id": "fmt/18",
        "evidence": [{"format_disclosure": "Full"}],
        "urls": {"pronom": "https://pronom.nationalarchives.gov.uk/fmt/18"},
    })
    mapping = {
        "source_type": "pronom_registry",
        "mapping_version": "2026-08-16-approved",
        "criteria_version": "v1",
        "claim_review_status": "approved",
        "decided_by": "QNL DCPA",
        "maps": [
            {
                "id": "pronom.disclosure.from_format_disclosure.v1",
                "criterion": "sustainability.disclosure",
                "from_collection": "evidence",
                "from_field": "format_disclosure",
                "directness": "explicit",
                "covers": "full",
                "source_independence": "independent",
                "mapping_status": "accepted",
                "values": {"Full": "public_specification"},
            },
            {
                "id": "pronom.disclosure.from_pronom_url_presence.v1",
                "criterion": "sustainability.disclosure",
                "from_field": "urls.pronom",
                "directness": "inferred",
                "covers": "partial",
                "source_independence": "independent",
                "mapping_status": "accepted",
                "when_present": "partial_specification",
            },
        ],
    }

    result = backfill_criterion_claims(store=store, criteria=CRITERIA, mappings=[mapping], dry_run=True)

    assert result["mapping_rules"] == {
        "pronom.disclosure.from_format_disclosure.v1": 1,
        "pronom.disclosure.from_pronom_url_presence.v1": 1,
    }
