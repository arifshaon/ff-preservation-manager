import pytest

from registry_builder.rebuild_store import (
    _assert_no_duplicate_active_mapping_rules,
    _duplicate_active_mapping_rules,
)


def _mapping(version: str, status: str = "accepted") -> dict:
    return {
        "source_type": "nara_digital_preservation_framework",
        "mapping_version": version,
        "review_status": "approved" if status in {"accepted", "approved"} else "draft",
        "maps": [
            {
                "id": "nara.rubric.5_1.technical_hardware_dependency.v1",
                "criterion": "technical.hardware_dependency",
                "mapping_status": status,
            }
        ],
    }


def test_duplicate_active_mapping_rule_is_rejected():
    mappings = [_mapping("approved-a"), _mapping("approved-b")]

    duplicates = _duplicate_active_mapping_rules(mappings)

    assert len(duplicates) == 1
    with pytest.raises(ValueError, match="Duplicate active criterion mapping rules detected"):
        _assert_no_duplicate_active_mapping_rules(mappings)


def test_approved_and_draft_copy_of_same_rule_are_allowed():
    mappings = [_mapping("approved-a"), _mapping("draft-b", status="needs_review")]

    assert _duplicate_active_mapping_rules(mappings) == []
    _assert_no_duplicate_active_mapping_rules(mappings)
