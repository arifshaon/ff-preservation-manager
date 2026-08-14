from registry_builder.models import CanonicalFormat
from registry_builder.validate import validate_registry


def test_duplicate_qnl_policy_identifier_is_warning_not_silent():
    registry = [
        CanonicalFormat(
            canonical_id="fmt-pdf-x-a",
            preferred_name="PDF/X row A",
            qnl_policy_overlay=[{"qnl_format_id": "QNL_200_PDFX", "source_row": 10}],
        ),
        CanonicalFormat(
            canonical_id="fmt-pdf-x-b",
            preferred_name="PDF/X row B",
            qnl_policy_overlay=[{"qnl_format_id": "QNL_200_PDFX", "source_row": 11}],
        ),
    ]
    errors, warnings = validate_registry(registry)
    assert errors == []
    assert any("QNL policy identifier QNL_200_PDFX" in warning for warning in warnings)
