from __future__ import annotations

from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.storage_status import build_storage_status, _validate_expectations


def test_storage_status_uses_latest_completed_source_contribution():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-1",
        "started_at": "2026-08-20T10:00:00+00:00",
        "finished_at": "2026-08-20T10:01:00+00:00",
        "sources": [
            {"source_id": "dpc_bit_list_2025", "status": "completed"},
        ],
    })
    store.save_source_record({
        "run_id": "run-1",
        "source_id": "dpc_bit_list_2025",
        "source_record_id": "old-1",
        "record_role": "evidence_only",
    })

    store.create_run({
        "run_id": "run-2",
        "started_at": "2026-08-21T10:00:00+00:00",
        "finished_at": "2026-08-21T10:01:00+00:00",
        "sources": [
            {"source_id": "dpc_bit_list_2025", "status": "completed"},
        ],
    })
    for idx in range(2):
        store.save_source_record({
            "run_id": "run-2",
            "source_id": "dpc_bit_list_2025",
            "source_record_id": f"new-{idx}",
            "record_role": "evidence_only",
        })
    store.save_snapshot({
        "run_id": "run-2",
        "source_id": "dpc_bit_list_2025",
        "sha256": "abc123",
    })

    status = build_storage_status(store)

    assert status["historical_source_record_count"] == 3
    assert status["current_canonical_format_count"] == 0
    latest = status["latest_sources"]["dpc_bit_list_2025"]
    assert latest["run_id"] == "run-2"
    assert latest["record_count"] == 2
    assert latest["record_role_counts"] == {"evidence_only": 2}
    assert latest["snapshot_sha256"] == ["abc123"]


def test_storage_status_expectations_report_mismatch():
    status = {
        "current_canonical_format_count": 1,
        "latest_sources": {
            "dpc_bit_list_2025": {
                "record_count": 84,
                "record_role_counts": {"evidence_only": 84},
            }
        },
    }

    assert _validate_expectations(
        status,
        source_id="dpc_bit_list_2025",
        expected_records=84,
        expected_evidence_only=84,
        expected_canonical=0,
    ) == ["Expected 0 current canonical formats, found 1"]
