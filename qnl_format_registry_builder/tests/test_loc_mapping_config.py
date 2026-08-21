from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import build_criterion_claims, load_mapping, validate_mapping


ROOT = Path(__file__).resolve().parents[1]


def _load_loc_pair():
    draft = load_mapping(ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v1.draft.json")
    approved = load_mapping(ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v1.approved.json")
    return draft, approved


def test_loc_draft_and_approved_mappings_validate_against_criteria():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    draft, approved = _load_loc_pair()

    draft_errors, draft_warnings = validate_mapping(draft, criteria)
    approved_errors, approved_warnings = validate_mapping(approved, criteria)

    assert draft_errors == []
    assert draft_warnings == []
    assert approved_errors == []
    assert approved_warnings == []


def test_loc_approved_mapping_uses_same_rule_set_as_draft():
    draft, approved = _load_loc_pair()

    draft_rules = {rule["id"]: rule for rule in draft["maps"]}
    approved_rules = {rule["id"]: rule for rule in approved["maps"]}

    assert set(draft_rules) == set(approved_rules)
    assert {rule["mapping_status"] for rule in draft_rules.values()} == {"needs_review"}
    assert {rule["mapping_status"] for rule in approved_rules.values()} == {"accepted"}
    assert draft["claim_review_status"] == "unreviewed"
    assert approved["claim_review_status"] == "approved"
    for rule_id, draft_rule in draft_rules.items():
        approved_rule = approved_rules[rule_id]
        assert draft_rule["criterion"] == approved_rule["criterion"]
        assert draft_rule["from_field"] == approved_rule["from_field"]
        assert draft_rule.get("values") == approved_rule.get("values")
        assert draft_rule.get("text_rules") == approved_rule.get("text_rules")


def test_loc_mapping_keeps_identity_fields_out_of_criterion_rules():
    draft, approved = _load_loc_pair()
    for mapping in (draft, approved):
        mapped_fields = {rule["from_field"] for rule in mapping["maps"]}
        excluded_fields = {item["field"] for item in mapping.get("excluded_from_criteria", [])}
        assert "urls.loc" in excluded_fields
        assert "loc_ids" in excluded_fields
        assert "puids" in excluded_fields
        assert "wikidata_ids" in excluded_fields
        assert "urls.loc" not in mapped_fields
        assert "loc_ids" not in mapped_fields
        assert "puids" not in mapped_fields
        assert "wikidata_ids" not in mapped_fields


def test_loc_mapping_projects_only_the_official_seven_sustainability_factors():
    _, approved = _load_loc_pair()
    mapped_fields = {rule["from_field"] for rule in approved["maps"]}
    assert mapped_fields == {
        "native_fields.sustainability_factors.disclosure",
        "native_fields.sustainability_factors.adoption",
        "native_fields.sustainability_factors.transparency",
        "native_fields.sustainability_factors.self_documentation",
        "native_fields.sustainability_factors.external_dependencies",
        "native_fields.sustainability_factors.impact_of_patents",
        "native_fields.sustainability_factors.technical_protection_mechanisms",
    }
    assert all("documentation" not in field.replace("self_documentation", "") for field in mapped_fields)


def test_loc_pdf_embedded_font_dependency_maps_to_low_external_dependency():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    _, approved = _load_loc_pair()
    canonical = {
        "canonical_id": "loc-fdd000030",
        "current": True,
        "source_records": [
            {
                "source_id": "loc_fdd_xml",
                "source_type": "loc_fdd_xml",
                "source_record_id": "fdd000030",
            }
        ],
    }
    source_record = {
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "source_record_id": "fdd000030",
        "native_fields": {
            "sustainability_factors": {
                "external_dependencies": (
                    "Faithful rendering requires that fonts be embedded. "
                    "PDF/A, PDF/X, and PDF/E-1 require that fonts be embedded."
                )
            }
        },
    }

    claims = build_criterion_claims([canonical], [source_record], [approved], criteria)

    assert [claim["criterion_id"] for claim in claims] == ["sustainability.external_dependencies"]
    assert claims[0]["mapping_rule_id"] == "loc.external_dependencies.from_sustainability_factor.v1"
    assert claims[0]["value"] == "low"
    assert claims[0]["review_status"] == "approved"
