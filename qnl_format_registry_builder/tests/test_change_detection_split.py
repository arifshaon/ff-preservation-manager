from registry_builder.change_detection import detect_registry_changes


def _record(canonical_id, source_records):
    return {
        "canonical_id": canonical_id,
        "preferred_name": canonical_id,
        "category": "example",
        "identifiers": {},
        "source_records": source_records,
        "hazard_assessment": {"band": "Low", "basis": "external_only", "review_required": False},
    }


def test_existing_canonical_redistributing_source_records_is_reported_as_split_not_additions():
    previous = [
        _record(
            "puid-fmt-720",
            [
                {"source_id": "pronom_registry", "source_record_id": "fmt/720"},
                {"source_id": "loc_fdd_xml", "source_record_id": "fdd-a"},
                {"source_id": "loc_fdd_xml", "source_record_id": "fdd-b"},
            ],
        )
    ]
    current = [
        _record(
            "puid-fmt-720",
            [{"source_id": "pronom_registry", "source_record_id": "fmt/720"}],
        ),
        _record(
            "loc-fdd-a",
            [{"source_id": "loc_fdd_xml", "source_record_id": "fdd-a"}],
        ),
        _record(
            "loc-fdd-b",
            [{"source_id": "loc_fdd_xml", "source_record_id": "fdd-b"}],
        ),
    ]

    report = detect_registry_changes(
        previous,
        current,
        run_id="run-split",
        created_at="2026-08-21T00:00:00+00:00",
    )

    split_events = [change for change in report["changes"] if change["change_type"] == "canonical_split"]
    assert len(split_events) == 1
    event = split_events[0]
    assert event["previous_canonical_id"] == "puid-fmt-720"
    assert event["current_canonical_ids"] == ["loc-fdd-a", "loc-fdd-b", "puid-fmt-720"]
    assert "record_added" not in report["raw_change_counts"]
    assert "record_removed" not in report["raw_change_counts"]
