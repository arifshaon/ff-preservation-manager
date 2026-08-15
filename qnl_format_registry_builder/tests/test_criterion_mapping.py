import pytest

from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_mapping import (
    MappingError,
    backfill_criterion_claims,
    build_criterion_claims,
    validate_mapping,
)
from registry_builder.storage.memory import MemoryRegistryStore


CRITERIA = CriteriaVocabulary({
    "criteria_version": "v1",
    "criteria": {
        "sustainability.disclosure": {
            "kind": "ordinal",
            "values": ["public_specification", "partial_specification", "proprietary_documented", "undocumented"],
            "null_value": "unknown",
        },
        "sustainability.external_dependencies": {
            "kind": "ordinal",
            "values": ["none", "low", "moderate", "high"],
            "null_value": "unknown",
        },
    },
})


QNL_MAPPING = {
    "source_type": "qnl_institution_format_evidence",
    "mapping_version": "2026-08-15",
    "criteria_version": "v1",
    "native_vocabulary": "qnl_seed",
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
            "values": {"publicly_documented_and_well_understood": "public_specification"},
        }
    ],
}


def _canonical_pdf():
    return {
        "canonical_id": "puid-fmt-18",
        "preferred_name": "PDF",
        "current": True,
        "source_records": [
            {
                "source_id": "qnl_seed",
                "source_type": "qnl_institution_format_evidence",
                "source_record_id": "qnl-evidence-pdf",
            }
        ],
        "institution_evidence_claims": [
            {
                "claim_id": "claim-1",
                "institution_id": "qnl",
                "criterion_id": "sustainability.disclosure",
                "evidence_value": "publicly_documented_and_well_understood",
            }
        ],
    }


def test_validate_mapping_rejects_hazard_conclusion_as_criterion():
    mapping = {
        "source_type": "nara_digital_preservation_framework",
        "mapping_version": "2026-08-15",
        "criteria_version": "v1",
        "decided_by": "reviewer",
        "maps": [
            {
                "criterion": "sustainability.disclosure",
                "from_field": "NARA Risk Level",
                "directness": "explicit",
                "covers": "full",
                "mapping_status": "accepted",
                "values": {"Low": "public_specification"},
            }
        ],
    }

    errors, _warnings = validate_mapping(mapping, CRITERIA)

    assert any("hazard/risk conclusion" in error for error in errors)


def test_validate_mapping_rejects_url_presence_as_public_specification():
    mapping = {
        "source_type": "pronom_registry",
        "mapping_version": "2026-08-15",
        "criteria_version": "v1",
        "maps": [
            {
                "criterion": "sustainability.disclosure",
                "from_field": "urls.pronom",
                "directness": "inferred",
                "covers": "partial",
                "mapping_status": "draft",
                "when_present": "public_specification",
            }
        ],
    }

    errors, _warnings = validate_mapping(mapping, CRITERIA)

    assert any("field presence cannot assert public_specification" in error for error in errors)


def test_build_criterion_claims_from_institution_evidence_claims():
    claims = build_criterion_claims([_canonical_pdf()], [], [QNL_MAPPING], CRITERIA)

    assert len(claims) == 1
    claim = claims[0]
    assert claim["canonical_id"] == "puid-fmt-18"
    assert claim["criterion_id"] == "sustainability.disclosure"
    assert claim["value"] == "public_specification"
    assert claim["source_type"] == "qnl_institution_format_evidence"
    assert claim["institution_id"] == "qnl"
    assert claim["confidence"] == "medium"
    assert claim["review_status"] == "unreviewed"


def test_backfill_writes_criterion_claims_to_store():
    store = MemoryRegistryStore()
    store.upsert_canonical_format(_canonical_pdf())

    result = backfill_criterion_claims(
        store=store,
        criteria=CRITERIA,
        mappings=[QNL_MAPPING],
    )

    assert result["claims_generated"] == 1
    stored = store.query("criterion_claims")
    assert len(stored) == 1
    assert stored[0]["mapping_rule_id"] == "qnl.disclosure.v1"


def test_backfill_rejects_invalid_mappings_before_writing():
    store = MemoryRegistryStore()
    bad = {
        "source_type": "nara",
        "mapping_version": "2026-08-15",
        "criteria_version": "v1",
        "maps": [
            {
                "criterion": "sustainability.external_dependencies",
                "from_field": "NARA Preferred Processing and Transformation Tool(s)",
                "directness": "explicit",
                "covers": "full",
                "mapping_status": "draft",
                "values": {"Tool": "low"},
            }
        ],
    }

    with pytest.raises(MappingError):
        backfill_criterion_claims(store=store, criteria=CRITERIA, mappings=[bad])
