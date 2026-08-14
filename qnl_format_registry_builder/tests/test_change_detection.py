from registry_builder.change_detection import detect_registry_changes


def _record(canonical_id, *, band="Low", basis="external_only", native=None, review=False):
    hazard = {"band": band, "basis": basis, "review_required": review}
    if native is not None:
        hazard["external_rating_native"] = native
        hazard["external_rating_native_direction"] = "higher_is_safer"
    return {
        "canonical_id": canonical_id,
        "preferred_name": canonical_id,
        "category": "example",
        "identifiers": {"extension": [canonical_id.replace("fmt-", "")]},
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
