def test_adapter_registry_imports_all_builtin_adapters():
    from registry_builder.adapters import ADAPTERS, resolve_adapter

    assert "loc_fdd_xml" in ADAPTERS
    assert "qnl_institution_format_evidence" in ADAPTERS
    assert resolve_adapter("loc_fdd_xml").type_name == "loc_fdd_xml"
    assert resolve_adapter("qnl_institution_format_evidence").type_name == "qnl_institution_format_evidence"
