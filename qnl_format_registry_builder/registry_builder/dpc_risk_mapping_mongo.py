from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any

from registry_builder.external_risk_mapping import apply_external_risk_mappings, load_external_risk_mapping
from registry_builder.models import CanonicalFormat, RawFormatRecord
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore


_DEFAULT_MAPPING = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "external_risk_mappings"
    / "dpc_bit_list_2025.v1.approved.json"
)
_CANONICAL_FIELDS = {field.name for field in fields(CanonicalFormat)}


def _load_config(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Pipeline config must contain a JSON object")
    storage = data.get("storage")
    if not isinstance(storage, dict):
        raise ValueError("Pipeline config must contain a storage object")
    return data


def _canonical_from_store(row: dict[str, Any]) -> CanonicalFormat:
    return CanonicalFormat(**{key: value for key, value in row.items() if key in _CANONICAL_FIELDS})


def _dpc_record_from_store(row: dict[str, Any]) -> RawFormatRecord:
    return RawFormatRecord(
        source_id=str(row.get("source_id") or ""),
        source_type=str(row.get("source_type") or ""),
        source_record_id=str(row.get("source_record_id") or "") or None,
        record_role=str(row.get("record_role") or "format_identity"),
        name=row.get("name"),
        category=row.get("category"),
        description=row.get("description"),
        urls=dict(row.get("urls") or {}),
        risk_assessments=[dict(item) for item in (row.get("risk_assessments") or [])],
        evidence=[dict(item) for item in (row.get("evidence") or [])],
        native_fields=dict(row.get("native_fields") or {}),
        raw=dict(row.get("raw") or {}),
    )


def _latest_completed_source_run_id(store: RegistryStore, source_id: str) -> str | None:
    latest: tuple[tuple[str, str], str] | None = None
    for run in store.query("runs"):
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        source_completed = any(
            str(item.get("source_id") or "") == source_id and item.get("status") == "completed"
            for item in (run.get("sources") or [])
        )
        if not source_completed:
            continue
        sort_key = (str(run.get("finished_at") or run.get("started_at") or run_id), run_id)
        if latest is None or sort_key > latest[0]:
            latest = (sort_key, run_id)
    return latest[1] if latest else None


def _latest_source_records(store: RegistryStore, source_id: str) -> tuple[str | None, list[RawFormatRecord]]:
    rows = store.query("source_records", {"source_id": source_id})
    latest_run_id = _latest_completed_source_run_id(store, source_id)
    if latest_run_id:
        rows = [row for row in rows if str(row.get("run_id") or "") == latest_run_id]
    elif rows:
        latest_run_id = max(str(row.get("run_id") or "") for row in rows)
        rows = [row for row in rows if str(row.get("run_id") or "") == latest_run_id]
    return latest_run_id, [_dpc_record_from_store(row) for row in rows]


def preview_dpc_risk_mapping(
    store: RegistryStore,
    mapping: dict[str, Any],
    *,
    include_drafts: bool = False,
) -> dict[str, Any]:
    source_id = str(mapping.get("source_id") or "dpc_bit_list_2025")
    registry = [_canonical_from_store(row) for row in store.get_current_registry_view()]
    by_id = {fmt.canonical_id: fmt for fmt in registry}
    previous_risk = {
        fmt.canonical_id: dict(fmt.synthesized_risk or {})
        for fmt in registry
    }
    latest_run_id, records = _latest_source_records(store, source_id)

    report = apply_external_risk_mappings(
        registry,
        records,
        mapping,
        include_drafts=include_drafts,
    )

    applied: list[dict[str, Any]] = []
    for item in report.get("applied", []):
        row = dict(item)
        targets: list[dict[str, Any]] = []
        for canonical_id in item.get("target_canonical_ids", []):
            fmt = by_id.get(canonical_id)
            if fmt is None:
                continue
            mapped = [
                assessment
                for assessment in fmt.risk_assessments
                if assessment.get("mapping_rule_id") == item.get("rule_id")
                and assessment.get("source_id") == source_id
            ]
            targets.append({
                "canonical_id": fmt.canonical_id,
                "preferred_name": fmt.preferred_name,
                "category": fmt.category,
                "identifiers": fmt.identifiers,
                "previous_synthesized_risk": previous_risk.get(fmt.canonical_id) or {},
                "projected_synthesized_risk": dict(fmt.synthesized_risk or {}),
                "mapped_assessments": mapped,
            })
        row["targets"] = targets
        applied.append(row)

    report["applied"] = applied
    report.update({
        "mode": "read_only_store_preview",
        "storage_write": False,
        "identity_projection": False,
        "current_canonical_format_count": len(registry),
        "source_id": source_id,
        "latest_source_run_id": latest_run_id,
        "dpc_evidence_record_count": len(records),
        "dpc_evidence_only_count": sum(1 for record in records if record.record_role == "evidence_only"),
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.dpc_risk_mapping_mongo",
        description=(
            "Read-only preview of reviewed DPC Bit List risk mappings against the "
            "current persistent registry. No canonical or assessment records are written."
        ),
    )
    parser.add_argument(
        "--config",
        default="config/sources.qnl.dpc-only.json",
        help="Pipeline config containing the persistent storage block",
    )
    parser.add_argument("--mapping", default=str(_DEFAULT_MAPPING), help="Reviewed DPC mapping JSON")
    parser.add_argument("--out", help="Optional JSON report path")
    parser.add_argument("--include-drafts", action="store_true")
    args = parser.parse_args()

    config = _load_config(args.config)
    store = create_store(config["storage"])
    try:
        mapping = load_external_risk_mapping(args.mapping)
        report = preview_dpc_risk_mapping(store, mapping, include_drafts=args.include_drafts)
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
