from registry_builder.adapters import ADAPTERS


def test_source_adapter_registry_contains_nara_adapter():
    assert "nara_preservation_csv" in ADAPTERS
