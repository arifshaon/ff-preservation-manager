from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mapping, validate_mapping


ROOT = Path(__file__).resolve().parents[1]


def _load_pronom_pair():
    draft = load_mapping(
        ROOT / "config" / "criterion_mappings" / "pronom_registry.v1.draft.json"
    )
    approved = load_mapping(
        ROOT / "config" / "criterion_mappings" / "pronom_registry.v1.approved.json"
    )
    return draft, approved


def test_pronom_draft_and_approved_mappings_validate_against_criteria():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    draft, approved = _load_pronom_pair()

    draft_errors, draft_warnings = validate_mapping(draft, criteria)
    approved_errors, approved_warnings = validate_mapping(approved, criteria)

    assert draft_errors == []
    assert draft_warnings == []
    assert approved_errors == []
    assert approved_warnings == []


def test_pronom_approved_mapping_uses_same_rule_set_as_draft():
    draft, approved = _load_pronom_pair()

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
        assert draft_rule.get("from_collection") == approved_rule.get("from_collection")
        assert draft_rule.get("values") == approved_rule.get("values")
        assert draft_rule.get("when_present") == approved_rule.get("when_present")
        assert draft_rule.get("transform") == approved_rule.get("transform")


def test_pronom_mapping_keeps_risk_like_fields_out_of_criterion_rules():
    draft, approved = _load_pronom_pair()
    for mapping in (draft, approved):
        mapped_fields = {rule["from_field"] for rule in mapping["maps"]}
        excluded_fields = {item["field"] for item in mapping.get("excluded_from_criteria", [])}
        assert "formatRisk" in excluded_fields
        assert "raw.record.formatRisk" in excluded_fields
        assert "formatRisk" not in mapped_fields
        assert "raw.record.formatRisk" not in mapped_fields
