from registry_builder.method_profiles import assign_method_profiles, build_preservation_method
from registry_builder.models import CanonicalFormat


def test_cml_inherits_xml_and_chemistry_profiles():
    config = {
        "version": "test-method-profiles-v1",
        "profiles": {
            "generic_preservation": {"steps": ["Preserve original"]},
            "structured_text": {"inherits": ["generic_preservation"], "validation": ["Check text readability"]},
            "xml_based_structured_text": {"inherits": ["structured_text"], "validation": ["Check XML well-formedness"]},
            "scientific_data": {"inherits": ["generic_preservation"], "metadata_extraction": ["Extract scientific context"]},
            "chemistry_scientific_data": {
                "inherits": ["scientific_data"],
                "metadata_extraction": ["Extract molecule identifiers"],
                "overrides": ["Use chemistry-aware derivative workflows"],
            },
        },
        "assignment_rules": [
            {"profile": "xml_based_structured_text", "match": {"identifiers": {"extension": ["cml"]}}},
            {
                "profile": "chemistry_scientific_data",
                "match": {
                    "identifiers": {"extension": ["cml"]},
                    "name_contains": ["chemical markup language"],
                },
            },
        ],
    }
    fmt = CanonicalFormat(
        canonical_id="fmt-chemical-markup-language-cml",
        preferred_name="Chemical Markup Language (CML)",
        identifiers={"extension": ["cml"]},
    )

    assign_method_profiles([fmt], config)

    method = fmt.preservation_method
    assert method["profile_version"] == "test-method-profiles-v1"
    assert method["assigned_profile_ids"] == [
        "generic_preservation",
        "structured_text",
        "xml_based_structured_text",
        "scientific_data",
        "chemistry_scientific_data",
    ]
    assert "Check XML well-formedness" in method["validation"]
    assert "Extract molecule identifiers" in method["metadata_extraction"]
    assert "Use chemistry-aware derivative workflows" in method["overrides"]


def test_build_preservation_method_deduplicates_inherited_steps():
    config = {
        "version": "test-method-profiles-v1",
        "profiles": {
            "base": {"steps": ["Preserve original"]},
            "child": {"inherits": ["base"], "steps": ["Preserve original", "Validate structure"]},
        },
    }

    method = build_preservation_method(["child"], config)

    assert method["steps"] == ["Preserve original", "Validate structure"]
