from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_mapping import build_criterion_claims


def _fixture():
    criteria = CriteriaVocabulary({
        "criteria_version": "v1",
        "criteria": {
            "sustainability.adoption": {
                "kind": "ordinal",
                "values": ["high", "low"],
                "null_value": "unknown",
            }
        },
    })
    canonical = [{
        "canonical_id": "puid-fmt-14",
        "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
        "identifiers": {"puid": ["fmt/14"]},
        "source_records": [{
            "source_id": "loc_fdd_xml",
            "source_type": "loc_fdd_xml",
            "source_record_id": "fdd000316",
            "relationship": "explicit_puid_cross_reference",
            "evidence_scope": "multi_puid_source_record",
            "related_puids": ["fmt/14", "fmt/15", "fmt/16", "fmt/17"],
        }],
    }]
    source_records = [{
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "source_record_id": "fdd000316",
        "native_fields": {"sustainability_factors": {"adoption": "Widely adopted"}},
    }]
    mapping = {
        "source_type": "loc_fdd_xml",
        "mapping_version": "test-v1",
        "criteria_version": "v1",
        "claim_review_status": "approved",
        "review_status": "approved",
        "decided_by": "test",
        "maps": [{
            "id": "loc.adoption.test",
            "criterion": "sustainability.adoption",
            "from_field": "native_fields.sustainability_factors.adoption",
            "directness": "explicit",
            "covers": "partial",
            "mapping_status": "accepted",
            "text_rules": [{"contains_any": ["widely adopted"], "value": "high"}],
        }],
    }
    return criteria, canonical, source_records, mapping


def test_related_source_record_does_not_generate_deterministic_claim_by_default():
    criteria, canonical, source_records, mapping = _fixture()

    claims = build_criterion_claims(canonical, source_records, [mapping], criteria)

    assert claims == []


def test_related_source_record_requires_explicit_mapping_opt_in():
    criteria, canonical, source_records, mapping = _fixture()
    mapping["allow_related_source_records"] = True

    claims = build_criterion_claims(canonical, source_records, [mapping], criteria)

    assert len(claims) == 1
    claim = claims[0]
    assert claim["canonical_id"] == "puid-fmt-14"
    assert claim["criterion_id"] == "sustainability.adoption"
    assert claim["value"] == "high"
    assert claim["source_record_id"] == "fdd000316"
    assert claim["relationship"] == "explicit_puid_cross_reference"
    assert claim["evidence_scope"] == "multi_puid_source_record"
    assert claim["related_puids"] == ["fmt/14", "fmt/15", "fmt/16", "fmt/17"]
