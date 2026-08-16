from registry_builder.pipeline import _criterion_claim_summary


def test_criterion_claim_summary_reports_mapped_source_with_zero_claims():
    summary = _criterion_claim_summary(
        claims=[
            {
                "source_id": "pronom_registry",
                "criterion_id": "sustainability.disclosure",
            }
        ],
        source_summaries=[
            {
                "source_id": "loc_fdd_xml",
                "source_type": "loc_fdd_xml",
                "enabled": True,
                "required": False,
                "status": "unavailable",
                "snapshots": 0,
                "records_extracted": 0,
            },
            {
                "source_id": "pronom_registry",
                "source_type": "pronom_registry",
                "enabled": True,
                "required": True,
                "status": "completed",
                "snapshots": 1,
                "records_extracted": 1,
            },
        ],
        mappings=[
            {"source_type": "loc_fdd_xml"},
            {"source_type": "pronom_registry"},
        ],
    )

    assert summary["claims_generated"] == 1
    assert summary["claims_by_source"] == {
        "loc_fdd_xml": 0,
        "pronom_registry": 1,
    }

    by_source = {
        item["source_id"]: item
        for item in summary["source_claim_status"]
    }
    assert by_source["loc_fdd_xml"] == {
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "enabled": True,
        "required": False,
        "source_run_status": "unavailable",
        "snapshots": 0,
        "records_extracted": 0,
        "claims_generated": 0,
        "criterion_mapping_configured": True,
        "contributes_claims": False,
    }
    assert by_source["pronom_registry"]["claims_generated"] == 1
    assert by_source["pronom_registry"]["contributes_claims"] is True


def test_criterion_claim_summary_reports_mapping_without_configured_source():
    summary = _criterion_claim_summary(
        claims=[],
        source_summaries=[],
        mappings=[{"source_type": "loc_fdd_xml"}],
    )

    assert summary["claims_by_source"] == {"loc_fdd_xml": 0}
    assert summary["source_claim_status"] == [
        {
            "source_id": "loc_fdd_xml",
            "source_type": None,
            "enabled": False,
            "required": None,
            "source_run_status": "not_configured",
            "snapshots": 0,
            "records_extracted": 0,
            "claims_generated": 0,
            "criterion_mapping_configured": True,
            "contributes_claims": False,
        }
    ]
