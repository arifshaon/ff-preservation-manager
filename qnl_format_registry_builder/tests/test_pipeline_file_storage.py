from __future__ import annotations

import json

from registry_builder.pipeline import run_pipeline
from registry_builder.storage.file import FileRegistryStore


def _write_source(path, records):
    path.write_text(json.dumps({"records": records}), encoding="utf-8")


def _write_config(path, source_path, store_path, *, source_id="test_source"):
    path.write_text(
        json.dumps(
            {
                "storage": {"type": "file", "path": str(store_path)},
                "exports": {"enabled": False},
                "method_profiles": {"enabled": False},
                "sources": [
                    {
                        "id": source_id,
                        "type": "standard_json",
                        "enabled": True,
                        "uris": [str(source_path)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_pipeline_persists_to_file_store_without_exports(tmp_path):
    source_path = tmp_path / "source.json"
    _write_source(
        source_path,
        [
            {
                "source_record_id": "pdf-a",
                "name": "PDF/A",
                "extensions": ["pdf"],
                "hazard": {"band": "Low", "rating": 1.0},
                "institution_policy": {
                    "institution_id": "qnl",
                    "institution_format_id": "QNL-PDFA",
                    "local_risk_level": "Low Risk",
                },
            }
        ],
    )
    store_path = tmp_path / "registry_store"
    config_path = tmp_path / "config.json"
    _write_config(config_path, source_path, store_path)

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "output")

    assert report["storage"]["type"] == "file"
    assert report["exports_enabled"] is False
    assert report["canonical_formats"] == 1
    assert report["raw_records_extracted"] == 1
    assert report["active_source_records"] == 1
    assert report["change_detection"]["run_kind"] == "baseline"
    assert len(list((store_path / "runs").glob("*.json"))) == 1
    assert len(list((store_path / "source_snapshots").glob("*.json"))) == 1
    assert len(list((store_path / "source_records").glob("*.json"))) == 1
    assert len(list((store_path / "canonical_formats").glob("*.json"))) == 1
    assert len(list((store_path / "institution_policy_overlays").glob("*.json"))) == 1
    assert len(list((store_path / "hazard_assessments").glob("*.json"))) == 1
    assert not (tmp_path / "output" / "registry.json").exists()


def test_pipeline_second_file_store_run_persists_change_events(tmp_path):
    source_path = tmp_path / "source.json"
    store_path = tmp_path / "registry_store"
    config_path = tmp_path / "config.json"
    _write_config(config_path, source_path, store_path)

    _write_source(
        source_path,
        [
            {"source_record_id": "a", "name": "Format A", "extensions": ["aa"], "hazard": {"band": "Low", "rating": 1.0, "native_rating": 30, "native_direction": "higher_is_safer"}},
            {"source_record_id": "b", "name": "Format B", "extensions": ["bb"], "hazard": {"band": "Low", "rating": 1.0}},
        ],
    )
    baseline = run_pipeline(config_path, tmp_path / "work1", tmp_path / "output1")
    assert baseline["change_detection"]["run_kind"] == "baseline"

    _write_source(
        source_path,
        [
            {"source_record_id": "a", "name": "Format A", "extensions": ["aa"], "hazard": {"band": "High", "rating": 3.0, "native_rating": -30, "native_direction": "higher_is_safer"}},
            {"source_record_id": "c", "name": "Format C", "extensions": ["cc"], "hazard": {"band": "Low", "rating": 1.0}},
        ],
    )
    change_run = run_pipeline(config_path, tmp_path / "work2", tmp_path / "output2")

    assert change_run["change_detection"]["run_kind"] == "change"
    counts = change_run["change_detection"]["change_counts"]
    assert counts["record_added"] == 1
    assert counts["record_removed"] == 1
    assert counts["hazard_band_changed"] == 1
    change_files = list((store_path / "assessment_changes").glob("*.json"))
    change_types = {json.loads(path.read_text(encoding="utf-8"))["change_type"] for path in change_files}
    assert {"record_added", "record_removed", "hazard_band_changed"}.issubset(change_types)

    current_records = [json.loads(path.read_text(encoding="utf-8")) for path in (store_path / "canonical_formats").glob("*.json")]
    removed = next(record for record in current_records if record["canonical_id"] == "fmt-format-b")
    assert removed["current"] is False
    assert removed["last_removed_run_id"] == change_run["run_id"]


def test_source_by_source_runs_reuse_prior_evidence_and_augment_canonical_record(tmp_path):
    store_path = tmp_path / "registry_store"

    nara_source = tmp_path / "nara.json"
    _write_source(
        nara_source,
        [
            {
                "source_record_id": "nara-pdf",
                "name": "Portable Document Format",
                "extensions": ["pdf"],
                "hazard": {"band": "Moderate", "rating": 2.0},
            }
        ],
    )
    nara_config = tmp_path / "nara-config.json"
    _write_config(nara_config, nara_source, store_path, source_id="nara_test")

    first = run_pipeline(nara_config, tmp_path / "work-nara", tmp_path / "out-nara")
    assert first["canonical_formats"] == 1
    assert first["raw_records_extracted"] == 1
    assert first["prior_source_records_reused"] == 0
    assert first["active_source_records"] == 1

    pronom_source = tmp_path / "pronom.json"
    _write_source(
        pronom_source,
        [
            {
                "source_record_id": "pronom-pdf",
                "name": "Portable Document Format",
                "extensions": ["pdf"],
                "hazard": {"band": "Low", "rating": 1.0},
            }
        ],
    )
    pronom_config = tmp_path / "pronom-config.json"
    _write_config(pronom_config, pronom_source, store_path, source_id="pronom_test")

    second = run_pipeline(pronom_config, tmp_path / "work-pronom", tmp_path / "out-pronom")

    assert second["canonical_formats"] == 1
    assert second["raw_records_extracted"] == 1
    assert second["prior_source_records_reused"] == 1
    assert second["active_source_records"] == 2
    assert second["change_detection"]["change_counts"].get("record_removed", 0) == 0

    store = FileRegistryStore({"type": "file", "path": str(store_path)})
    current = store.get_current_registry_view()
    assert len(current) == 1
    assert current[0]["preferred_name"] == "Portable Document Format"
    assert len(current[0]["source_records"]) == 2
    assert {item["source_id"] for item in current[0]["source_records"]} == {"nara_test", "pronom_test"}
