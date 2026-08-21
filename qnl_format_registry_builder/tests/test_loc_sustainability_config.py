import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_loc_sustainability_config_uses_reviewed_source_and_only_loc_mapping():
    config = json.loads((ROOT / "config" / "sources.qnl.loc-sustainability.json").read_text(encoding="utf-8"))

    assert config["storage"]["database"] == "qnl_format_registry"
    assert config["incremental_source_updates"] is True
    assert config["criterion_mapping"] == {
        "enabled": True,
        "mode": "apply",
        "criteria": "criteria/v1.json",
        "mappings": "criterion_mappings/loc_fdd_xml.v1.approved.json",
        "include_drafts": False,
        "scope": "all",
        "notes": config["criterion_mapping"]["notes"],
    }
    assert len(config["sources"]) == 1
    assert config["sources"][0]["id"] == "loc_fdd_xml"
    assert config["sources"][0]["type"] == "loc_fdd_xml_reviewed"
    assert config["identifier_kinds"]["puid"]["verified_from"] == ["pronom_registry", "pronom_droid_xml"]


def test_loc_approved_mapping_contains_no_overall_risk_projection():
    mapping = json.loads(
        (ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v1.approved.json").read_text(encoding="utf-8")
    )

    assert len(mapping["maps"]) == 7
    assert all(str(rule["criterion"]).startswith("sustainability.") for rule in mapping["maps"])
    forbidden = ("risk", "hazard", "overall", "recommendation", "action")
    assert all(not any(token in str(rule["criterion"]).lower() for token in forbidden) for rule in mapping["maps"])
