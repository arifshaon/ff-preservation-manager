from registry_builder.adapters import ADAPTERS


def test_source_adapter_registry_contains_source_level_adapters_and_aliases():
    assert "nara_digital_preservation_framework" in ADAPTERS
    assert "pronom_registry" in ADAPTERS
    assert "wikidata_sparql" in ADAPTERS
    # Compatibility aliases / representation-specific adapters remain available.
    assert "nara_preservation_csv" in ADAPTERS
    assert "pronom_droid_xml" in ADAPTERS
