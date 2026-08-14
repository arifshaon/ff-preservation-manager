import pytest

from registry_builder.adapters.qnl_policy_xlsx import _field, _get, _resolve_field_map


def test_get_does_not_fuzzy_bind_format_to_qnl_format_id():
    row = {"qnl_format_id": "QNL_099_Comma_Separated_Values", "digital_file": "Comma Separated Values"}
    assert _get(row, ["format"]) == ""
    assert _get(row, ["digital_file"]) == "Comma Separated Values"


def test_configured_field_map_resolves_digital_file_header():
    raw_headers = ["QNL Format ID", "Digital file", "File Extension(s)"]
    field_map = _resolve_field_map({"field_map": {"name": "Digital file"}}, raw_headers)
    row = {"qnl_format_id": "QNL_095_Chemical_Markup_Language_(CML)", "digital_file": "Chemical Markup Language"}
    assert _field(row, field_map, "name", ["format"]) == "Chemical Markup Language"


def test_configured_field_map_missing_column_fails_loudly():
    with pytest.raises(ValueError):
        _resolve_field_map({"field_map": {"name": "Digital file"}}, ["QNL Format ID", "File Extension(s)"])
