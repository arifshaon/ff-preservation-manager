from registry_builder.models import CanonicalFormat
from registry_builder.validate import summarize_validation_warnings, validate_registry, validation_warning_counts


def test_duplicate_institution_policy_identifier_is_warning_not_silent():
    registry = [
        CanonicalFormat(
            canonical_id="fmt-pdf-x-a",
            preferred_name="PDF/X row A",
            institution_policy_overlays=[
                {"institution_id": "qnl", "institution_format_id": "QNL_200_PDFX", "source_row": 10}
            ],
        ),
        CanonicalFormat(
            canonical_id="fmt-pdf-x-b",
            preferred_name="PDF/X row B",
            institution_policy_overlays=[
                {"institution_id": "qnl", "institution_format_id": "QNL_200_PDFX", "source_row": 11}
            ],
        ),
    ]
    errors, warnings = validate_registry(registry)
    assert errors == []
    assert any("institutional policy identifier qnl:QNL_200_PDFX" in warning for warning in warnings)


def test_validation_warnings_are_grouped_by_type():
    warnings = [
        "weak identifier mime:image/x-wpg appears in multiple canonical records: ['a', 'b']",
        "weak identifier mime:image/x-wpg appears in multiple canonical records: ['c', 'd']",
        "institutional policy identifier qnl:QNL_200_PDFX appears in multiple source rows/canonical records: ['a', 'b']",
    ]

    summary = summarize_validation_warnings(warnings, sample_limit=1)
    counts = validation_warning_counts(warnings)

    assert counts == {"institution_policy_duplicate": 1, "weak_identifier_overlap": 2}
    assert summary["weak_identifier_overlap"]["count"] == 2
    assert len(summary["weak_identifier_overlap"]["samples"]) == 1
    assert summary["institution_policy_duplicate"]["count"] == 1
