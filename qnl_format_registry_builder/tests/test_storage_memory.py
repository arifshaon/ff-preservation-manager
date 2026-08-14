from __future__ import annotations

from registry_builder.storage.memory import MemoryRegistryStore


def test_memory_store_current_view_and_identifier_lookup():
    store = MemoryRegistryStore()
    run_id = store.create_run({"run_id": "test-run"})
    assert run_id == "test-run"

    store.upsert_canonical_format({"canonical_id": "puid-fmt-353", "preferred_name": "TIFF"})
    store.upsert_identifier({"format_id": "puid-fmt-353", "type": "puid", "value": "fmt/353"})
    store.save_institution_policy_overlay({
        "format_id": "puid-fmt-353",
        "institution_id": "qnl",
        "institution_format_id": "QNL-TIFF",
    })

    current_view = store.get_current_registry_view()
    assert current_view[0]["preferred_name"] == "TIFF"
    assert store.find_by_identifier("puid", "fmt/353")["canonical_id"] == "puid-fmt-353"
    assert store.list_institution_policy_formats()[0]["canonical_id"] == "puid-fmt-353"
    assert store.list_institution_policy_formats("qnl")[0]["canonical_id"] == "puid-fmt-353"

    # Returned records should be defensive copies, not direct internal objects.
    current_view[0]["preferred_name"] = "Changed"
    assert store.get_current_registry_view()[0]["preferred_name"] == "TIFF"
