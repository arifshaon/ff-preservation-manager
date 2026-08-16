from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mapping, validate_mapping


ROOT = Path(__file__).resolve().parents[1]


def test_full_nara_mapping_config_validates_against_criteria_vocabulary():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mapping = load_mapping(
        ROOT
        / "config"
        / "criterion_mappings"
        / "nara_digital_preservation_framework.v1.draft.json"
    )

    errors, warnings = validate_mapping(mapping, criteria)

    assert errors == []
    assert warnings == []
    assert len(mapping["maps"]) == 27
    assert {rule["mapping_status"] for rule in mapping["maps"]} == {"needs_review"}


def test_nara_mapping_keeps_conclusions_and_decisions_out_of_criterion_rules():
    mapping = load_mapping(
        ROOT
        / "config"
        / "criterion_mappings"
        / "nara_digital_preservation_framework.v1.draft.json"
    )

    mapped_fields = {rule["from_field"] for rule in mapping["maps"]}
    forbidden_fragments = [
        "Risk Level",
        "Numeric Risk Rating",
        "NARA TOTAL",
        "TOTAL Disclosure Score",
        "TOTAL Adoption Score",
        "TOTAL Transparency Score",
        "TOTAL Self-Documentation Score",
        "TOTAL External Hardware Dependencies Score",
        "TOTAL External Software Dependencies Score",
        "TOTAL Impact of Patents Score",
        "TOTAL Technical Protection Mechanisms Score",
        "Preservation Action",
        "Proposed Preservation Plan",
        "Preferred Processing and Transformation Tool",
        "Transfer Guidance",
        "Feasibility Score",
    ]

    assert all(
        fragment not in field
        for field in mapped_fields
        for fragment in forbidden_fragments
    )
    excluded_fields = {item["field"] for item in mapping.get("excluded_from_criteria", [])}
    assert "Risk Level" in excluded_fields
    assert "TOTAL Numeric Risk Rating" in excluded_fields
    assert "NARA Preservation Action" in excluded_fields
    assert "Feasibility Score" in excluded_fields
