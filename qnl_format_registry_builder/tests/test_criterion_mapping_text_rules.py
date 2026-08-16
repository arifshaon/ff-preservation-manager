from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_mapping import build_criterion_claims, validate_mapping


CRITERIA = CriteriaVocabulary({
    "criteria_version": "v1",
    "criteria": {
        "sustainability.disclosure": {
            "kind": "ordinal",
            "values": ["public_specification", "partial_specification", "proprietary_documented", "undocumented"],
            "null_value": "unknown",
        }
    },
})


MAPPING = {
    "source_type": "loc_fdd_xml",
    "mapping_version": "2026-08-16-approved",
    "criteria_version": "v1",
    "native_vocabulary": "loc_fdd_xml",
    "claim_review_status": "approved",
    "decided_by": "QNL DCPA",
    "maps": [
        {
            "id": "loc.disclosure.text_rule.v1",
            "criterion": "sustainability.disclosure",
            "from_field": "native_fields.sustainability_factors.disclosure",
            "directness": "derived",
            "covers": "partial",
            "source_independence": "independent",
            "mapping_status": "accepted",
            "text_rules": [
                {
                    "value": "public_specification",
                    "contains_any": ["fully disclosed", "published specification"],
                }
            ],
        }
    ],
}


def test_text_rule_mapping_validates_and_builds_claim():
    errors, warnings = validate_mapping(MAPPING, CRITERIA)

    assert errors == []
    assert warnings == []

    canonical = {
        "canonical_id": "loc-fdd000001",
        "current": True,
        "source_records": [
            {
                "source_id": "loc_fdd_xml",
                "source_type": "loc_fdd_xml",
                "source_record_id": "fdd000001",
            }
        ],
    }
    source_record = {
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "source_record_id": "fdd000001",
        "native_fields": {
            "sustainability_factors": {
                "disclosure": "Fully disclosed. The published specification is available from the standards body."
            }
        },
    }

    claims = build_criterion_claims([canonical], [source_record], [MAPPING], CRITERIA)

    assert len(claims) == 1
    assert claims[0]["mapping_rule_id"] == "loc.disclosure.text_rule.v1"
    assert claims[0]["value"] == "public_specification"
    assert claims[0]["source_value"].startswith("Fully disclosed")
    assert claims[0]["review_status"] == "approved"
