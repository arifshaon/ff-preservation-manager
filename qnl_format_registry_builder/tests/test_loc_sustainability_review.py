from registry_builder.loc_sustainability_review import review_loc_sustainability_preview


def test_loc_sustainability_review_reports_coverage_and_unmapped_samples():
    raw_records = [
        {
            "source_record_id": "fdd000001",
            "native_fields": {
                "sustainability_factors": {
                    "disclosure": "Fully disclosed.",
                    "technical_protection_mechanisms": "None.",
                }
            },
        },
        {
            "source_record_id": "fdd000002",
            "native_fields": {
                "sustainability_factors": {
                    "disclosure": "Unusual disclosure wording.",
                    "technical_protection_mechanisms": "See related format.",
                }
            },
        },
    ]
    claims = [
        {
            "source_record_id": "fdd000001",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
        },
        {
            "source_record_id": "fdd000001",
            "criterion_id": "sustainability.tpm_encryption",
            "value": "none_or_not_applicable",
        },
    ]

    report = review_loc_sustainability_preview(raw_records, claims, unmatched_sample_limit=5)

    disclosure = report["factors"]["disclosure"]
    assert disclosure["records_with_factor"] == 2
    assert disclosure["records_with_claim"] == 1
    assert disclosure["records_unmapped"] == 1
    assert disclosure["coverage_percent"] == 50.0
    assert disclosure["claim_value_counts"] == {"public_specification": 1}
    assert disclosure["unmapped_samples"][0]["source_record_id"] == "fdd000002"

    tpm = report["factors"]["technical_protection_mechanisms"]
    assert tpm["records_with_factor"] == 2
    assert tpm["records_with_claim"] == 1
    assert tpm["records_unmapped"] == 1
