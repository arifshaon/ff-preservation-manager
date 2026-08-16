import json

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


PRONOM_MAPPING = {
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
        }
    ],
}


LOC_MAPPING = {
    "source_type": "loc_fdd_xml",
    "mapping_version": "2026-08-16-approved",
    "criteria_version": "v1",
    "claim_review_status": "approved",
    "decided_by": "QNL DCPA",
    "maps": [
        {
            "id": "loc.disclosure.from_sustainability_factor.v1",
            "criterion": "sustainability.disclosure",
            "from_field": "native_fields.sustainability_factors.disclosure",
            "directness": "derived",
            "covers": "partial",
            "source_independence": "independent",
            "mapping_status": "accepted",
            "values": {"Open standard": "public_specification"},
        }
    ],
}


def test_criterion_evidence_audit_counts_corrobation_across_strong_aliases(tmp_path):
    store = MemoryRegistryStore()
    store.upsert_canonical_format({
        "canonical_id": "fmt-pdf",
        "preferred_name": "PDF",
        "current": True,
        "identifiers": {
            "puid": ["fmt/18"],
            "loc": ["fdd000030"],
        },
        "source_records": [],
    })
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-18",
        "preferred_name": "PDF via PRONOM",
        "current": True,
        "source_records": [
            {
                "source_id": "pronom_registry",
                "source_type": "pronom_registry",
                "source_record_id": "fmt/18",
            }
        ],
    })
    store.upsert_canonical_format({
        "canonical_id": "loc-fdd000030",
        "preferred_name": "PDF via LOC",
        "current": True,
        "source_records": [
            {
                "source_id": "loc_fdd_xml",
                "source_type": "loc_fdd_xml",
                "source_record_id": "fdd000030",
            }
        ],
    })
    store.save_source_record({
        "source_id": "pronom_registry",
        "source_type": "pronom_registry",
        "source_record_id": "fmt/18",
        "evidence": [{"format_disclosure": "Full"}],
    })
    store.save_source_record({
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "source_record_id": "fdd000030",
        "native_fields": {
            "sustainability_factors": {
                "disclosure": "Open standard",
            }
        },
    })

    mappings_dir = tmp_path / "mappings"
    mappings_dir.mkdir()
    (mappings_dir / "pronom.json").write_text(json.dumps(PRONOM_MAPPING), encoding="utf-8")
    (mappings_dir / "loc.json").write_text(json.dumps(LOC_MAPPING), encoding="utf-8")

    report = run_criterion_evidence_audit(store, criteria=CRITERIA, mappings_path=mappings_dir)

    disclosure = report["accepted_mapping_coverage"]["sustainability.disclosure"]
    assert report["coverage_identity_normalization"] == "strong_identifier_aliases"
    assert disclosure["formats_with_any_claim"] == 1
    assert disclosure["formats_with_2plus_independent_sources"] == 1
    assert disclosure["contributing_sources"] == ["loc_fdd_xml", "pronom_registry"]
