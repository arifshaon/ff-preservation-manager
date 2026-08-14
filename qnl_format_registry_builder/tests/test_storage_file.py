from __future__ import annotations

import json

from registry_builder.storage import STORAGE_BACKENDS
from registry_builder.storage.file import FileRegistryStore


def test_file_store_persists_collection_json_documents(tmp_path):
    store = FileRegistryStore({"path": str(tmp_path / "store")})

    run_id = store.create_run({"run_id": "test-run", "status": "running"})
    assert run_id == "test-run"

    store.save_snapshot({
        "run_id": run_id,
        "source_id": "source-a",
        "sha256": "abc123",
        "uri": "memory://source-a",
    })
    store.save_source_record({
        "run_id": run_id,
        "source_id": "source-a",
        "source_record_id": "row-1",
        "name": "Tagged Image File Format",
    })
    store.upsert_canonical_format({
        "run_id": run_id,
        "canonical_id": "puid-fmt-353",
        "preferred_name": "Tagged Image File Format",
    })
    store.upsert_identifier({
        "run_id": run_id,
        "format_id": "puid-fmt-353",
        "type": "puid",
        "value": "fmt/353",
        "source": "pronom_registry",
    })
    store.save_institution_policy_overlay({
        "run_id": run_id,
        "format_id": "puid-fmt-353",
        "institution_id": "qnl",
        "institution_format_id": "QNL-TIFF",
    })
    store.save_hazard_assessment({
        "run_id": run_id,
        "format_id": "puid-fmt-353",
        "basis": "corroborated",
        "band": "Low",
    })

    root = tmp_path / "store"
    assert (root / "runs" / "test-run.json").exists()
    assert len(list((root / "canonical_formats").glob("*.json"))) == 1
    assert len(list((root / "format_identifiers").glob("*.json"))) == 1
    assert len(list((root / "hazard_assessments").glob("*.json"))) == 1

    current_view = store.get_current_registry_view()
    assert current_view[0]["preferred_name"] == "Tagged Image File Format"
    assert store.find_by_identifier("puid", "fmt/353")["canonical_id"] == "puid-fmt-353"
    assert store.list_institution_policy_formats("qnl")[0]["canonical_id"] == "puid-fmt-353"

    run_doc = json.loads((root / "runs" / "test-run.json").read_text(encoding="utf-8"))
    assert run_doc["status"] == "running"


def test_file_store_is_registered():
    assert "file" in STORAGE_BACKENDS
    assert "json_file" in STORAGE_BACKENDS
