from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.evidence_packs import build_evidence_pack
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.identity_evidence import derive_registry_identity_evidence


def _framework():
    return RiskFramework.from_dict({
        "framework_id": "registry-recognition-test",
        "version": "1",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 1.0,
            "bands": [{"band": "Low", "min_score": 0, "max_score": 2}],
        },
        "questions": [
            {
                "id": "q_registry_recognition",
                "evidence_fields": ["identification.registry_recognition"],
                "evidence_value_map": {
                    "formal_registry_identifier": "low_risk",
                    "partial_registry_coverage": "moderate_risk",
                    "no_formal_identifier": "high_risk",
                },
                "answers": [
                    {"id": "low_risk", "points": 0},
                    {"id": "moderate_risk", "points": 1},
                    {"id": "high_risk", "points": 2},
                    {"id": "unknown", "points": 0, "abstention": True},
                ],
            }
        ],
    })


def test_verified_puid_derives_registry_recognition_evidence_and_answer():
    record = {
        "canonical_id": "puid-fmt-276",
        "preferred_name": "Acrobat PDF 1.7 - Portable Document Format",
        "identifiers": {"puid": ["fmt/276"], "mime": ["application/pdf"]},
        "identifier_claims": [
            {
                "kind": "puid",
                "value": "fmt/276",
                "source": "pronom_registry",
                "verified": True,
                "source_record_id": "fmt/276",
            }
        ],
    }

    pack = build_evidence_pack(record)
    derived = derive_answers(_framework(), pack)

    recognition = [
        row for row in pack["global_evidence"]
        if row.get("criterion_id") == "identification.registry_recognition"
    ]
    assert len(recognition) == 1
    assert recognition[0]["value"] == "formal_registry_identifier"
    assert recognition[0]["verified_puids"][0]["value"] == "fmt/276"
    assert derived["answers"]["q_registry_recognition"] == "low_risk"
    assert derived["derivation"]["q_registry_recognition"]["status"] == "derived"


def test_unverified_copied_puid_does_not_create_registry_recognition_evidence():
    record = {
        "canonical_id": "fmt-copied",
        "preferred_name": "Copied Identifier Example",
        "identifiers": {"puid": ["fmt/276"]},
        "identifier_claims": [
            {
                "kind": "puid",
                "value": "fmt/276",
                "source": "wikidata_file_formats",
                "verified": False,
                "source_record_id": "Q26085317",
            }
        ],
    }

    assert derive_registry_identity_evidence(record) == []
    pack = build_evidence_pack(record)
    derived = derive_answers(_framework(), pack)
    assert derived["answers"]["q_registry_recognition"] == "unknown"
    assert derived["derivation"]["q_registry_recognition"]["status"] == "missing_evidence"


def test_other_verified_authority_ids_do_not_imply_automated_registry_recognition():
    record = {
        "canonical_id": "loc-fdd000277",
        "preferred_name": "PDF 1.7",
        "identifier_claims": [
            {"kind": "loc", "value": "fdd000277", "source": "loc_fdd_xml", "verified": True},
            {"kind": "nara", "value": "NF00369", "source": "nara_digital_preservation_framework", "verified": True},
        ],
    }

    assert derive_registry_identity_evidence(record) == []
