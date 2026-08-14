from registry_builder.models import CanonicalFormat
from registry_builder.pipeline import _method_profile_metrics


def test_method_profile_metrics_exclude_generic_baseline_from_averages():
    registry = [
        CanonicalFormat(
            canonical_id="fmt-a",
            preferred_name="A",
            preservation_method={
                "direct_profile_ids": ["structured_data"],
                "assigned_profile_ids": ["generic_preservation", "structured_text", "structured_data"],
            },
        ),
        CanonicalFormat(
            canonical_id="fmt-b",
            preferred_name="B",
            preservation_method={
                "direct_profile_ids": ["xml_based_structured_text", "chemistry_scientific_data"],
                "assigned_profile_ids": [
                    "generic_preservation",
                    "structured_text",
                    "xml_based_structured_text",
                    "scientific_data",
                    "chemistry_scientific_data",
                ],
            },
        ),
        CanonicalFormat(canonical_id="fmt-c", preferred_name="C"),
    ]

    metrics = _method_profile_metrics(registry)

    assert metrics["formats_with_method_profiles"] == 2
    assert metrics["generic_preservation_count"] == 2
    assert metrics["non_discriminating_method_profiles"] == ["generic_preservation"]
    assert metrics["average_direct_discriminating_method_profiles_per_format"] == 1.0
    assert metrics["average_effective_discriminating_method_profiles_per_format"] == 2.0
    assert metrics["average_direct_method_profiles_per_format"] == 1.0
    assert metrics["average_effective_method_profiles_per_format"] == 2.0
    assert metrics["max_direct_discriminating_method_profiles_per_format"] == 2
    assert metrics["max_effective_discriminating_method_profiles_per_format"] == 4
    assert metrics["direct_method_profile_distribution"] == {
        "chemistry_scientific_data": 1,
        "structured_data": 1,
        "xml_based_structured_text": 1,
    }
    assert metrics["effective_method_profile_distribution"] == {
        "chemistry_scientific_data": 1,
        "scientific_data": 1,
        "structured_data": 1,
        "structured_text": 2,
        "xml_based_structured_text": 1,
    }
