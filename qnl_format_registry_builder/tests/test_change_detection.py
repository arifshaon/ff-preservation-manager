from registry_builder.change_detection import detect_registry_changes


def _record(
    canonical_id,
    *,
    band="Low",
    basis="external_only",
    native=None,
    review=False,
    external_band=None,
    institution_band=None,
    source_records=None,
):
    hazard = {"band": band, "basis": basis, "review_required": review}
    if external_band is not None:
        hazard["external_band"] = external_band
    if institution_band is not None:
        hazard["institution_band"] = institution_band
    if native is not None:
        hazard["external_rating_native"] = native
        hazard["external_rating_native_direction"] = "higher_is_safer"
    return {
        "canonical_id": canonical_id,
        "preferred_name": canonical_id,
        "category": "example",
        "identifiers": {"extension": [canonical_id.replace("fmt-", "")]},
        "source_records": source_records if source_records is not None else [{"source_id": "nara"}],
        "hazard_assessment": hazard,
    }


def test_first_run_is_baseline_not_mass_record_added():
    report = detect_registry_changes([], [_record("fmt-a"), _record("fmt-b")], run_id="run-1", created_at="2026-08-14T00:00:00+00:00")

    assert report["run_kind"] == "baseline"
    assert report["previous_canonical_formats"] == 0
    assert report["current_canonical_formats"] == 2
    assert report["changes"] == []


def test_detects_added_removed_hazard_native_and_divergence_changes():
    previous = [
        _record("fmt-a", band="Low", basis="corroborated", native=30),
        _record("fmt-b", band="Low", basis="external_only", native=25),
        _record("fmt-c", band="Moderate", basis="corroborated", native=0),
    ]
    current = [
        _record("fmt-a", band="High", basis="institution_override", native=-30, review=True),
        _record("fmt-c", band="Moderate", basis="corroborated", native=-5),
        _record("fmt-d", band="Low", basis="external_only", native=33),
    ]

    report = detect_registry_changes(previous, current, run_id="run-2", created_at="2026-08-14T00:00:00+00:00")
    change_types = [change["change_type"] for change in report["changes"]]

    assert report["run_kind"] == "change"
    assert "record_added" in change_types
    assert "record_removed" in change_types
    assert "hazard_band_changed" in change_types
    assert "hazard_basis_changed" in change_types
    assert "external_rating_native_changed" in change_types
    assert "divergence_opened" in change_types
    assert report["change_counts"]["record_added"] == 1
    assert report["change_counts"]["record_removed"] == 1


def test_canonical_rekey_is_not_reported_as_added_and_removed():
    previous = [
        _record(
            "nara-nf00100",
            source_records=[
                {"source_id": "nara_digital_preservation_framework", "source_record_id": "NF00100"},
            ],
        )
    ]
    current = [
        _record(
            "puid-fmt-100",
            source_records=[
                {"source_id": "nara_digital_preservation_framework", "source_record_id": "NF00100"},
                {"source_id": "pronom_registry", "source_record_id": "fmt/100"},
            ],
        )
    ]

    report = detect_registry_changes(previous, current, run_id="run-rekey", created_at="2026-08-21T00:00:00+00:00")
    change_types = [change["change_type"] for change in report["changes"]]

    assert change_types == ["canonical_rekeyed"]
    event = report["changes"][0]
    assert event["previous_canonical_ids"] == ["nara-nf00100"]
    assert event["current_canonical_id"] == "puid-fmt-100"
    assert event["shared_source_records"] == [
        {"source_id": "nara_digital_preservation_framework", "source_record_id": "NF00100"}
    ]
    assert "record_added" not in report["raw_change_counts"]
    assert "record_removed" not in report["raw_change_counts"]


def test_multiple_previous_ids_absorbed_by_one_current_id_are_reported_as_merge():
    previous = [
        _record(
            "nara-a",
            source_records=[{"source_id": "nara", "source_record_id": "A"}],
        ),
        _record(
            "nara-b",
            source_records=[{"source_id": "nara", "source_record_id": "B"}],
        ),
    ]
    current = [
        _record(
            "puid-fmt-1",
            source_records=[
                {"source_id": "nara", "source_record_id": "A"},
                {"source_id": "nara", "source_record_id": "B"},
                {"source_id": "pronom", "source_record_id": "fmt/1"},
            ],
        )
    ]

    report = detect_registry_changes(previous, current, run_id="run-merge", created_at="2026-08-21T00:00:00+00:00")

    assert [change["change_type"] for change in report["changes"]] == ["canonical_merged"]
    event = report["changes"][0]
    assert event["previous_canonical_ids"] == ["nara-a", "nara-b"]
    assert event["current_canonical_id"] == "puid-fmt-1"
    assert "record_added" not in report["raw_change_counts"]
    assert "record_removed" not in report["raw_change_counts"]


def test_true_removal_without_persistent_provenance_remains_record_removed():
    previous = [
        _record(
            "nara-old",
            source_records=[{"source_id": "nara", "source_record_id": "OLD"}],
        )
    ]
    current = [
        _record(
            "puid-new",
            source_records=[{"source_id": "pronom", "source_record_id": "fmt/999"}],
        )
    ]

    report = detect_registry_changes(previous, current, run_id="run-remove", created_at="2026-08-21T00:00:00+00:00")
    change_types = [change["change_type"] for change in report["changes"]]

    assert "record_added" in change_types
    assert "record_removed" in change_types
    assert "canonical_rekeyed" not in change_types
    assert "canonical_merged" not in change_types


def test_review_required_without_two_disagreeing_estimators_is_not_divergence():
    previous = [
        _record("fmt-a", band="Low", basis="external_only", review=False),
    ]
    current = [
        _record("fmt-a", band="Unknown", basis="no_estimator_available", review=True),
    ]

    report = detect_registry_changes(previous, current, run_id="run-no-estimator", created_at="2026-08-14T00:00:00+00:00")
    change_types = [change["change_type"] for change in report["changes"]]

    assert "hazard_band_changed" in change_types
    assert "hazard_basis_changed" in change_types
    assert "divergence_opened" not in change_types
    assert "divergence_resolved" not in change_types


def test_two_present_estimators_with_different_bands_open_divergence():
    previous = [
        _record("fmt-a", band="Low", basis="corroborated", external_band="Low", institution_band="Low"),
    ]
    current = [
        _record("fmt-a", band="High", basis="institution_override", external_band="Low", institution_band="High", review=True),
    ]

    report = detect_registry_changes(previous, current, run_id="run-divergent", created_at="2026-08-14T00:00:00+00:00")
    change_types = [change["change_type"] for change in report["changes"]]

    assert "divergence_opened" in change_types


def test_bulk_change_type_collapses_to_source_coverage_event():
    previous = [_record(f"fmt-{i:03d}", native=30) for i in range(120)]
    current = [_record(f"fmt-{i:03d}", native=-30) for i in range(120)]

    report = detect_registry_changes(previous, current, run_id="run-3", created_at="2026-08-14T00:00:00+00:00")

    assert report["raw_change_counts"]["external_rating_native_changed"] == 120
    assert report["change_counts"] == {"source_coverage_changed": 1}
    assert report["changes"][0]["change_type"] == "source_coverage_changed"
    assert report["changes"][0]["collapsed_change_type"] == "external_rating_native_changed"
    assert report["changes"][0]["affected_count"] == 120
