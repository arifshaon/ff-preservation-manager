from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mapping, load_mappings, validate_mappings


ROOT = Path(__file__).resolve().parents[1]


def test_shipped_criteria_and_mapping_configs_validate():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mappings = load_mappings(ROOT / "config" / "criterion_mappings")

    errors, _warnings = validate_mappings(mappings, criteria)

    assert errors == []


def test_pronom_none_disclosure_is_unknown_not_undocumented():
    mapping = load_mapping(
        ROOT / "config" / "criterion_mappings" / "pronom_registry.v1.approved.json"
    )
    rule = next(
        item
        for item in mapping["maps"]
        if item["id"] == "pronom.disclosure.from_format_disclosure.v1"
    )

    assert rule["values"]["None"] == "unknown"
    assert rule["values"]["none"] == "unknown"
