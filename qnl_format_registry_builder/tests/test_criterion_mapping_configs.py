from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mappings, validate_mappings


ROOT = Path(__file__).resolve().parents[1]


def test_shipped_criteria_and_mapping_configs_validate():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mappings = load_mappings(ROOT / "config" / "criterion_mappings")

    errors, _warnings = validate_mappings(mappings, criteria)

    assert errors == []
