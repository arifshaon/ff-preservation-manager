from registry_builder.models import CanonicalFormat, Identifier, RawFormatRecord, SourceSnapshot
from registry_builder.pipeline import _exports_enabled, _persist_registry_to_store
from registry_builder.storage.memory import MemoryRegistryStore


def test_pipeline_persists_registry_objects_to_selected_store():
    store = MemoryRegistryStore()
    snapshot = SourceSnapshot(
        source_id="source-a",
        source_type="standard_json",
        uri="examples/source.json",
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path="work/snapshots/source-a/abc123.json",
    )
    raw = RawFormatRecord(
        source_id="source-a",
        source_type="standard_json",
        source_record_id="raw-1",
        name="Tagged Image File Format",
        extensions=["tif"],
        identifiers=[Identifier("puid", "fmt/353", "pronom_registry", True, "raw-1")],
    )
    fmt = CanonicalFormat(
        canonical_id="puid-fmt-353",
        preferred_name="Tagged Image File Format",
        identifiers={"extension": ["tif"], "puid": ["fmt/353"]},
        identifier_claims=[
            {"kind": "puid", "value": "fmt/353", "source": "pronom_registry", "verified": True, "source_record_id": "raw-1"}
        ],
        institution_policy_overlays=[{"institution_id": "qnl", "institution_format_id": "QNL-TIFF"}],
        hazard_assessment={"band": "Low", "basis": "corroborated"},
    )

    _persist_registry_to_store(
        store,
        run_id="run-test",
        snapshots=[snapshot],
        raw_records=[raw],
        registry=[fmt],
    )

    assert store.snapshots[0]["run_id"] == "run-test"
    assert store.source_records[0]["source_record_id"] == "raw-1"
    assert store.get_current_registry_view()[0]["canonical_id"] == "puid-fmt-353"
    assert store.find_by_identifier("puid", "fmt/353")["preferred_name"] == "Tagged Image File Format"
    assert store.institution_policy_overlays[0]["format_id"] == "puid-fmt-353"
    assert store.hazard_assessments[0]["basis"] == "corroborated"


def test_exports_can_be_disabled_for_database_only_runs():
    assert _exports_enabled({}) is True
    assert _exports_enabled({"exports": {"enabled": False}}) is False
    assert _exports_enabled({"exports": False}) is False
