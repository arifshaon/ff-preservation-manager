import pytest

from registry_builder.adapters.institution_policy_xlsx import _field, _get, _is_substantive_name, _resolve_field_map


def test_get_does_not_fuzzy_bind_format_to_institution_format_id():
    row = {"qnl_format_id": "QNL_099_Comma_Separated_Values", "digital_file": "Comma Separated Values"}
    assert _get(row, ["format"]) == ""
    assert _get(row, ["digital_file"]) == "Comma Separated Values"


def test_configured_field_map_resolves_digital_file_header():
    raw_headers = ["QNL Format ID", "Digital file", "File Extension(s)"]
    field_map = _resolve_field_map({"field_map": {"name": "Digital file"}}, raw_headers)
    row = {"qnl_format_id": "QNL_095_Chemical_Markup_Language_(CML)", "digital_file": "Chemical Markup Language"}
    assert _field(row, field_map, "name", ["format"]) == "Chemical Markup Language"


def test_configured_field_map_accepts_multiple_candidate_headers():
    raw_headers = ["QNL Format ID", "Digital file", "Description/Justification", "MIME type(s)", "Category/Plan(s)"]
    field_map = _resolve_field_map(
        {
            "field_map": {
                "description": ["Description and Justification", "Description/Justification"],
                "mime_types": ["MIME", "MIME type(s)"],
                "category": ["Category", "Category/Plan(s)"],
            }
        },
        raw_headers,
    )
    row = {
        "description_justification": "Domain-specific XML format for chemistry data",
        "mime_type_s": "chemical/x-cml",
        "category_plan_s": "Scientific data",
    }
    assert _field(row, field_map, "description", []) == "Domain-specific XML format for chemistry data"
    assert _field(row, field_map, "mime_types", []) == "chemical/x-cml"
    assert _field(row, field_map, "category", []) == "Scientific data"


def test_configured_field_map_missing_column_fails_loudly():
    with pytest.raises(ValueError):
        _resolve_field_map({"field_map": {"name": "Digital file"}}, ["QNL Format ID", "File Extension(s)"])


def test_configured_field_map_reports_all_missing_columns():
    with pytest.raises(ValueError) as exc:
        _resolve_field_map(
            {
                "field_map": {
                    "mime_types": ["MIME", "MIME Type"],
                    "category": ["Category/Plan", "Category"],
                    "preferred_tools": ["Preferred Processing and Conversion Tool(s)"],
                }
            },
            ["QNL Format ID", "Digital file", "File Extension(s)"],
        )
    message = str(exc.value)
    assert "mime_types" in message
    assert "category" in message
    assert "preferred_tools" in message


def test_non_substantive_names_are_rejected_before_matching():
    assert _is_substantive_name("Comma Separated Values") is True
    assert _is_substantive_name("?") is False
    assert _is_substantive_name("N/A") is False
    assert _is_substantive_name("-") is False
