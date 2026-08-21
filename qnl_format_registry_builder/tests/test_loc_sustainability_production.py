import json
from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mapping, source_claims_to_supersede, validate_mapping
from registry_builder.storage.memory import MemoryRegistryStore


ROOT = Path(__file__).resolve().parents[1]


def _draft2():
    return load_mapping(ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v2.draft2.json")


def _approved():
    return load_mapping(ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v2.approved.json")


def test_loc_v2_approved_mapping_validates_and_freezes_draft2_rule_semantics():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    draft = _draft2()
    approved = _approved()

    errors, warnings = validate_mapping(approved, criteria)

    assert errors == []
    assert warnings == []
    assert approved["review_status"] == "approved"
    assert approved["claim_review_status"] == "approved"
    assert approved["mapping_mode"] == "manual_approved"
    assert approved["mapping_version"] == "2026-08-21-v2-approved"

    draft_rules = {rule["id"]: rule for rule in draft["maps"]}
    approved_rules = {rule["id"]: rule for rule in approved["maps"]}
    assert set(approved_rules) == set(draft_rules)
    assert len(approved_rules) == 7

    for rule_id, draft_rule in draft_rules.items():
        approved_rule = approved_rules[rule_id]
        assert approved_rule["mapping_status"] == "accepted"
        assert approved_rule["criterion"] == draft_rule["criterion"]
        assert approved_rule["from_field"] == draft_rule["from_field"]
        assert approved_rule.get("values") == draft_rule.get("values")
        assert approved_rule.get("text_rules") == draft_rule.get("text_rules")
        assert approved_rule.get("rationale") == draft_rule.get("rationale")


def test_loc_source_refresh_keeps_inline_criterion_mapping_disabled_but_points_to_approved_v2():
    config = json.loads((ROOT / "config" / "sources.qnl.loc-sustainability.json").read_text(encoding="utf-8"))

    assert config["storage"]["database"] == "qnl_format_registry"
    assert config["incremental_source_updates"] is True
    assert config["criterion_mapping"]["enabled"] is False
    assert config["criterion_mapping"]["include_drafts"] is False
    assert config["criterion_mapping"]["mappings"] == "criterion_mappings/loc_fdd_xml.v2.approved.json"
    assert config["sources"] == [config["sources"][0]]
    assert config["sources"][0]["id"] == "loc_fdd_xml"
    assert config["sources"][0]["type"] == "loc_fdd_xml_reviewed"


def test_loc_production_backfill_uses_approved_mapping_and_source_replacement():
    config = json.loads(
        (ROOT / "config" / "loc_fdd_sustainability_backfill.production.json").read_text(encoding="utf-8")
    )

    assert config["storage"]["type"] == "mongodb"
    assert config["storage"]["database"] == "qnl_format_registry"
    assert config["criteria"] == "criteria/v1.json"
    assert config["mappings"] == "criterion_mappings/loc_fdd_xml.v2.approved.json"
    assert config["include_drafts"] is False
    assert config["replace_source_claims"] is True
    assert config["dry_run"] is False


def test_source_replacement_can_retire_loc_claim_when_current_mapping_emits_zero_claims():
    store = MemoryRegistryStore()
    store.save_criterion_claim(
        {
            "canonical_id": "loc-fdd000001",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "loc_fdd_xml",
            "source_type": "loc_fdd_xml",
            "source_record_id": "fdd000001",
            "mapping_rule_id": "loc.disclosure.from_sustainability_factor.v2",
            "current": True,
        }
    )

    superseded = source_claims_to_supersede(store, [], [_approved()])

    assert len(superseded) == 1
    assert superseded[0]["source_id"] == "loc_fdd_xml"
    assert superseded[0]["current"] is True
