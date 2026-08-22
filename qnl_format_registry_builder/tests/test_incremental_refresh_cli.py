from registry_builder.refresh import _compact_report, _selected_config


def test_selected_refresh_enables_only_requested_sources_and_forces_incremental_updates():
    config = {
        "incremental_source_updates": False,
        "sources": [
            {"id": "pronom", "type": "pronom", "enabled": True},
            {"id": "nara", "type": "nara_digital_preservation_framework", "enabled": True},
            {"id": "loc", "type": "loc_fdd_xml", "enabled": False},
        ],
    }

    selected, available = _selected_config(config, ["nara", "loc"])

    assert available == ["pronom", "nara", "loc"]
    assert selected["incremental_source_updates"] is True
    enabled = {source["id"]: source["enabled"] for source in selected["sources"]}
    assert enabled == {"pronom": False, "nara": True, "loc": True}
    assert config["incremental_source_updates"] is False
    assert config["sources"][2]["enabled"] is False


def test_selected_refresh_rejects_unknown_source():
    config = {"sources": [{"id": "pronom", "type": "pronom"}]}
    try:
        _selected_config(config, ["missing"])
    except ValueError as exc:
        assert "Unknown source ID" in str(exc)
        assert "pronom" in str(exc)
    else:
        raise AssertionError("unknown refresh source must be rejected")


def test_compact_refresh_report_exposes_reuse_and_change_state():
    report = {
        "status": "completed",
        "run_id": "run-1",
        "started_at": "start",
        "finished_at": "finish",
        "incremental_source_updates": True,
        "sources": [
            {"source_id": "nara", "status": "completed", "source_changed": True, "records_extracted": 12},
            {"source_id": "pronom", "status": "disabled", "source_changed": False, "records_extracted": 0},
        ],
        "raw_records_extracted": 12,
        "stored_source_records_used_for_augmentation": 100,
        "active_source_records": 112,
        "canonical_formats": 50,
        "change_detection": {"total_changes": 3},
        "risk_claim_materialization": {"claims_materialized": 20},
        "criterion_mapping": {"enabled": True, "claims_generated": 5},
        "outputs": ["run_report.json"],
    }

    compact = _compact_report(report, ["nara"])

    assert compact["refreshed_source_ids"] == ["nara"]
    assert compact["raw_records_extracted"] == 12
    assert compact["prior_source_records_reused"] == 100
    assert compact["active_source_records"] == 112
    assert compact["change_detection"]["total_changes"] == 3
