from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from registry_builder.storage import create_store


def _load_storage_config(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config must contain a JSON object")
    storage = data.get("storage") if isinstance(data.get("storage"), dict) else data
    if not isinstance(storage, dict):
        raise ValueError("No storage configuration found")
    return dict(storage)


def _latest_completed_source_runs(runs: list[dict[str, Any]]) -> dict[str, str]:
    latest: dict[str, tuple[tuple[str, str], str]] = {}
    for run in runs:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        timestamp = str(run.get("finished_at") or run.get("started_at") or run_id)
        sort_key = (timestamp, run_id)
        for source in run.get("sources") or []:
            if source.get("status") != "completed":
                continue
            source_id = str(source.get("source_id") or "")
            if not source_id:
                continue
            if source_id not in latest or sort_key > latest[source_id][0]:
                latest[source_id] = (sort_key, run_id)
    return {source_id: run_id for source_id, (_, run_id) in latest.items()}


def build_storage_status(store) -> dict[str, Any]:
    runs = store.query("runs")
    source_records = store.query("source_records")
    snapshots = store.query("source_snapshots")
    canonical = store.get_current_registry_view()
    latest_runs = _latest_completed_source_runs(runs)

    latest_sources: dict[str, Any] = {}
    for source_id, run_id in sorted(latest_runs.items()):
        records = [
            record
            for record in source_records
            if str(record.get("source_id") or "") == source_id
            and str(record.get("run_id") or "") == run_id
        ]
        source_snapshots = [
            snapshot
            for snapshot in snapshots
            if str(snapshot.get("source_id") or "") == source_id
            and str(snapshot.get("run_id") or "") == run_id
        ]
        roles = Counter(str(record.get("record_role") or "format_identity") for record in records)
        latest_sources[source_id] = {
            "run_id": run_id,
            "record_count": len(records),
            "record_role_counts": dict(sorted(roles.items())),
            "snapshot_count": len(source_snapshots),
            "snapshot_sha256": sorted(
                str(snapshot.get("sha256"))
                for snapshot in source_snapshots
                if snapshot.get("sha256")
            ),
        }

    return {
        "status": "ok",
        "run_count": len(runs),
        "historical_source_record_count": len(source_records),
        "historical_snapshot_count": len(snapshots),
        "current_canonical_format_count": len(canonical),
        "latest_sources": latest_sources,
    }


def _validate_expectations(
    status: dict[str, Any],
    *,
    source_id: str | None,
    expected_records: int | None,
    expected_evidence_only: int | None,
    expected_canonical: int | None,
) -> list[str]:
    errors: list[str] = []
    source = (status.get("latest_sources") or {}).get(source_id) if source_id else None
    if source_id and source is None:
        errors.append(f"No completed source contribution found for {source_id}")
        return errors
    if expected_records is not None and source is not None:
        actual = int(source.get("record_count", 0))
        if actual != expected_records:
            errors.append(f"Expected {expected_records} latest records for {source_id}, found {actual}")
    if expected_evidence_only is not None and source is not None:
        actual = int((source.get("record_role_counts") or {}).get("evidence_only", 0))
        if actual != expected_evidence_only:
            errors.append(
                f"Expected {expected_evidence_only} evidence_only records for {source_id}, found {actual}"
            )
    if expected_canonical is not None:
        actual = int(status.get("current_canonical_format_count", 0))
        if actual != expected_canonical:
            errors.append(f"Expected {expected_canonical} current canonical formats, found {actual}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.storage_status",
        description="Inspect persistent RegistryStore contents using latest successful source contributions.",
    )
    parser.add_argument("--config", required=True, help="Pipeline config or standalone storage config JSON")
    parser.add_argument("--expect-source", help="Source ID whose latest successful contribution must exist")
    parser.add_argument("--expect-records", type=int, help="Expected record count for --expect-source")
    parser.add_argument(
        "--expect-evidence-only",
        type=int,
        help="Expected evidence_only record count for --expect-source",
    )
    parser.add_argument("--expect-canonical", type=int, help="Expected current canonical format count")
    args = parser.parse_args()

    storage_config = _load_storage_config(args.config)
    store = create_store(storage_config)
    try:
        status = build_storage_status(store)
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    errors = _validate_expectations(
        status,
        source_id=args.expect_source,
        expected_records=args.expect_records,
        expected_evidence_only=args.expect_evidence_only,
        expected_canonical=args.expect_canonical,
    )
    status["expectation_status"] = "ok" if not errors else "error"
    status["expectation_errors"] = errors
    print(json.dumps(status, indent=2, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
