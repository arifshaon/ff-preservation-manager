import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_loc_sustainability_production_config_refreshes_source_without_inline_claim_writes():
    config = json.loads((ROOT / "config" / "sources.qnl.loc-sustainability.json").read_text(encoding="utf-8"))

    assert config["storage"]["database"] == "qnl_format_registry"
    assert config["incremental_source_updates"] is True
    assert config["criterion_mapping"]["enabled"] is False
    assert config["criterion_mapping"]["mappings"] == "criterion_mappings/loc_fdd_xml.v2.approved.json"
    assert config["criterion_mapping"]["include_drafts"] is False
    assert len(config["sources"]) == 1
    assert config["sources"][0]["id"] == "loc_fdd_xml"
    assert config["sources"][0]["type"] == "loc_fdd_xml_reviewed"
    assert config["identifier_kinds"]["puid"]["verified_from"] == ["pronom_registry", "pronom_droid_xml"]


def test_loc_sustainability_preview_is_memory_only_and_includes_v2_draft2():
    config = json.loads(
        (ROOT / "config" / "sources.qnl.loc-sustainability-preview.json").read_text(encoding="utf-8")
    )

    assert config["storage"] == {"type": "memory"}
    assert config["incremental_source_updates"] is False
    assert config["exports"]["enabled"] is True
    assert config["criterion_mapping"]["enabled"] is True
    assert config["criterion_mapping"]["mappings"] == "criterion_mappings/loc_fdd_xml.v2.draft2.json"
    assert config["criterion_mapping"]["include_drafts"] is True
    assert config["sources"][0]["type"] == "loc_fdd_xml_reviewed"


def test_loc_mappings_contain_no_overall_risk_projection():
    for filename in (
        "loc_fdd_xml.v1.approved.json",
        "loc_fdd_xml.v2.draft.json",
        "loc_fdd_xml.v2.draft2.json",
        "loc_fdd_xml.v2.approved.json",
    ):
        mapping = json.loads((ROOT / "config" / "criterion_mappings" / filename).read_text(encoding="utf-8"))

        assert len(mapping["maps"]) == 7
        assert all(str(rule["criterion"]).startswith("sustainability.") for rule in mapping["maps"])
        forbidden = ("risk", "hazard", "overall", "recommendation", "action")
        assert all(not any(token in str(rule["criterion"]).lower() for token in forbidden) for rule in mapping["maps"])
