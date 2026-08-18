from registry_builder.storage.file import FileRegistryStore
from registry_builder.storage.memory import MemoryRegistryStore


def _exercise_store(store):
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-14",
        "format_id": "puid-fmt-14",
        "preferred_name": "PDF 1.0",
        "identifiers": {"puid": ["fmt/14"], "extension": ["pdf"]},
        "current": True,
    })
    store.upsert_canonical_format({
        "canonical_id": "loc-fdd000316",
        "format_id": "loc-fdd000316",
        "preferred_name": "PDF Versions 1.0-1.3",
        "identifiers": {"loc": ["fdd000316"], "extension": ["pdf"]},
        "current": True,
    })

    # Historical/stale row left by an older reconciliation run. It must not be
    # treated as current identity once the canonical record no longer carries it.
    store.upsert_identifier({
        "run_id": "old-run",
        "format_id": "puid-fmt-14",
        "canonical_id": "puid-fmt-14",
        "type": "loc",
        "value": "fdd000316",
        "source": "nara_digital_preservation_framework",
        "verified": False,
    })

    assert store.find_by_identifier("puid", "fmt/14")["canonical_id"] == "puid-fmt-14"
    assert store.find_by_identifier("loc", "fdd000316")["canonical_id"] == "loc-fdd000316"
    assert store.find_by_identifier("loc", "missing") is None

    # If the true LOC canonical is retired, the stale row on the PUID canonical
    # still must not resurrect fdd000316 as an identifier of PDF 1.0.
    retired = store.find_by_identifier("loc", "fdd000316")
    store.upsert_canonical_format({**retired, "current": False})
    assert store.find_by_identifier("loc", "fdd000316") is None


def test_memory_store_uses_current_canonical_identifier_index():
    _exercise_store(MemoryRegistryStore())


def test_file_store_uses_current_canonical_identifier_index(tmp_path):
    _exercise_store(FileRegistryStore({"type": "file", "path": str(tmp_path / "store")}))
