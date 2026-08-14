import json

import pytest

from registry_builder.models import CanonicalFormat, Identifier, RawFormatRecord, SourceSnapshot
from registry_builder.pipeline import _exports_enabled, _persist_registry_to_store, run_pipeline
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


def _write_standard_source(path):
    path.write_text(
        json.dumps({"records": [{"source_record_id": "ok-1", "name": "Good Format", "extensions": ["good"]}]}),
        encoding="utf-8",
    )


def test_pipeline_records_optional_source_failure_and_continues(tmp_path):
    source_path = tmp_path / "source.json"
    _write_standard_source(source_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage": {"type": "memory"},
                "exports": {"enabled": False},
                "method_profiles": {"enabled": False},
                "sources": [
                    {"id": "good", "type": "standard_json", "enabled": True, "uris": [str(source_path)]},
                    {"id": "optional_bad", "type": "missing_adapter", "enabled": True, "required": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "out")

    assert report["canonical_formats"] == 1
    assert report["source_status_counts"]["completed"] == 1
    assert report["source_status_counts"]["failed"] == 1
    failed = next(source for source in report["sources"] if source["source_id"] == "optional_bad")
    assert failed["status"] == "failed"
    assert failed["required"] is False
    assert failed["error_type"] == "ValueError"


def test_pipeline_required_source_failure_still_aborts(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage": {"type": "memory"},
                "exports": {"enabled": False},
                "method_profiles": {"enabled": False},
                "sources": [
                    {"id": "required_bad", "type": "missing_adapter", "enabled": True, "required": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="No adapter registered"):
        run_pipeline(config_path, tmp_path / "work", tmp_path / "out")
