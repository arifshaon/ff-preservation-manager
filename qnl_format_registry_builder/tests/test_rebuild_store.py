import json

from registry_builder.models import RawFormatRecord
from registry_builder.rebuild_store import rebuild_registry_from_store
from registry_builder.storage.file import FileRegistryStore


def _save_source_record(store, run_id, record):
    payload = record.to_dict()
    payload["run_id"] = run_id
    store.save_source_record(payload)


def _setup_store(tmp_path):
    store_path = tmp_path / "store"
    store = FileRegistryStore({"type": "file", "path": str(store_path)})
    source_run = "run-source-1"
    store.create_run({
        "run_id": source_run,
        "started_at": "2026-08-17T00:00:00+00:00",
        "finished_at": "2026-08-17T00:01:00+00:00",
        "status": "completed",
        "sources": [
            {"source_id": "pronom_registry", "status": "completed"},
            {"source_id": "nara_digital_preservation_framework", "status": "completed"},
            {"source_id": "loc_fdd_xml", "status": "completed"},
        ],
    })

    _save_source_record(store, source_run, RawFormatRecord(
        source_id="pronom_registry",
        source_type="pronom_registry",
        source_record_id="fmt/14",
        name="Acrobat PDF 1.0 - Portable Document Format",
        extensions=["pdf"],
        mime_types=["application/pdf"],
        puids=["fmt/14"],
        version="1.0",
    ))
    _save_source_record(store, source_run, RawFormatRecord(
        source_id="nara_digital_preservation_framework",
        source_type="nara_digital_preservation_framework",
        source_record_id="NF00362",
        name="Portable Document Format (PDF) version 1.0",
        extensions=["pdf"],
        mime_types=["application/pdf"],
        puids=["fmt/14"],
        loc_ids=["fdd000316"],
        nara_ids=["NF00362"],
        hazard={"band": "Moderate", "rating": 2, "external_rating_native": 10},
    ))
    _save_source_record(store, source_run, RawFormatRecord(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        source_record_id="fdd000316",
        name="PDF_1_3, PDF Versions 1.0-1.3",
        extensions=["pdf"],
        puids=["fmt/14", "fmt/15", "fmt/16", "fmt/17"],
        loc_ids=["fdd000316"],
    ))
    for number, version in ((15, "1.1"), (16, "1.2"), (17, "1.3")):
        _save_source_record(store, source_run, RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id=f"fmt/{number}",
            name=f"Acrobat PDF {version}",
            extensions=["pdf"],
            puids=[f"fmt/{number}"],
            version=version,
        ))

    # Simulate the bad pre-fix current registry where NARA and LOC compete with
    # the PRONOM PUID record.
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-14",
        "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
        "identifiers": {"puid": ["fmt/14"]},
        "current": True,
    })
    store.upsert_canonical_format({
        "canonical_id": "nara-nf00362",
        "preferred_name": "Portable Document Format (PDF) version 1.0",
        "identifiers": {"puid": ["fmt/14"], "nara": ["NF00362"], "loc": ["fdd000316"]},
        "current": True,
    })
    store.upsert_canonical_format({
        "canonical_id": "loc-fdd000316",
        "preferred_name": "PDF_1_3, PDF Versions 1.0-1.3",
        "identifiers": {"puid": ["fmt/14", "fmt/15", "fmt/16", "fmt/17"], "loc": ["fdd000316"]},
        "current": True,
    })

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "pipeline_version": "test",
        "incremental_source_updates": True,
        "storage": {"type": "file", "path": str(store_path)},
        "exports": {"enabled": True},
        "method_profiles": {"enabled": False},
        "criterion_mapping": {"enabled": False},
        "identifier_kinds": {
            "puid": {"strength": "strong", "verified_from": ["pronom_registry"]},
            "loc": {"strength": "strong", "verified_from": ["loc_fdd_xml"]},
            "nara": {"strength": "strong", "verified_from": ["nara_digital_preservation_framework"]},
            "wikidata": {"strength": "weak", "verified_from": []},
        },
    }), encoding="utf-8")
    return store, source_run, config_path


def test_rebuild_from_store_dry_run_does_not_mutate_store(tmp_path):
    store, source_run, config_path = _setup_store(tmp_path)
    out_path = tmp_path / "dry-run"
    before = {row["canonical_id"]: row for row in store.get_current_registry_view()}

    report = rebuild_registry_from_store(config_path, out_path)

    after = {row["canonical_id"]: row for row in store.get_current_registry_view()}
    assert after == before
    assert "nara-nf00362" in after
    assert report["dry_run"] is True
    assert report["persisted"] is False
    assert report["status"] == "dry_run_completed"
    assert (out_path / "registry.json").is_file()
    assert (out_path / "run_report.json").is_file()
    assert {row["run_id"] for row in store.query("source_records")} == {source_run}


def test_rebuild_from_store_rereconciles_latest_source_records_without_acquisition(tmp_path):
    store, source_run, config_path = _setup_store(tmp_path)
    out_path = tmp_path / "applied"

    report = rebuild_registry_from_store(config_path, out_path, apply=True)

    current = {row["canonical_id"]: row for row in store.get_current_registry_view()}
    assert "puid-fmt-14" in current
    assert "nara-nf00362" not in current
    assert "loc-fdd000316" in current

    pdf10 = current["puid-fmt-14"]
    assert pdf10["preferred_name"] == "Acrobat PDF 1.0 - Portable Document Format"
    assert pdf10["version"] == "1.0"
    assert pdf10["identifiers"]["puid"] == ["fmt/14"]
    assert pdf10["identifiers"]["nara"] == ["NF00362"]
    assert "loc" not in pdf10["identifiers"]
    assert pdf10["hazard_assessment"]["band"] == "Moderate"
    assert pdf10["hazard_assessment"]["external_rating_native"] == 10
    assert any(
        ref.get("source_record_id") == "fdd000316"
        and ref.get("relationship") == "explicit_puid_cross_reference"
        for ref in pdf10["source_records"]
    )

    retired_nara = next(
        row for row in store.query("canonical_formats")
        if row["canonical_id"] == "nara-nf00362"
    )
    assert retired_nara["current"] is False

    # The repair run must not pretend that it reacquired or replaced source
    # records. Future incremental runs should still see the original completed
    # acquisition run as authoritative.
    assert all(source["status"] == "reused_from_store" for source in report["sources"])
    source_records_after = store.query("source_records")
    assert len(source_records_after) == 6
    assert {row["run_id"] for row in source_records_after} == {source_run}

    assert report["run_kind"] == "rebuild_from_store"
    assert report["dry_run"] is False
    assert report["persisted"] is True
    assert report["validation_errors"] == []
    assert (out_path / "registry.json").is_file()
    assert (out_path / "run_report.json").is_file()
