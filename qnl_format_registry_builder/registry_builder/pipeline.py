from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from registry_builder.adapters import ADAPTERS
from registry_builder.db import write_sqlite
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile
from registry_builder.utils import ensure_dir, write_csv, write_json, write_jsonl
from registry_builder.validate import validate_registry


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_pipeline(config_path: str | Path, workdir: str | Path, outdir: str | Path) -> dict[str, Any]:
    started_at = utc_now_iso()
    config = load_config(config_path)
    workdir = ensure_dir(workdir)
    outdir = ensure_dir(outdir)

    all_snapshots: list[SourceSnapshot] = []
    raw_records: list[RawFormatRecord] = []
    source_summaries: list[dict[str, Any]] = []

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            source_summaries.append({"source_id": source.get("id"), "enabled": False})
            continue
        source_type = source["type"]
        adapter_cls = ADAPTERS.get(source_type)
        if adapter_cls is None:
            raise ValueError(f"No adapter registered for source type: {source_type}")
        adapter = adapter_cls(source, workdir)
        snapshots = adapter.acquire()
        extracted = adapter.extract(snapshots)
        all_snapshots.extend(snapshots)
        raw_records.extend(normalize_record(r) for r in extracted)
        source_summaries.append({
            "source_id": source["id"],
            "source_type": source_type,
            "enabled": True,
            "snapshots": len(snapshots),
            "records_extracted": len(extracted),
        })

    registry = reconcile(raw_records)
    errors, warnings = validate_registry(registry)

    registry_dicts = [fmt.to_dict() for fmt in registry]
    write_jsonl(outdir / "registry.jsonl", registry_dicts)
    write_json(outdir / "registry.json", registry_dicts)
    write_jsonl(outdir / "raw_records.jsonl", [r.to_dict() for r in raw_records])
    write_json(outdir / "source_snapshots.json", [s.__dict__ for s in all_snapshots])

    csv_rows = []
    for fmt in registry:
        d = fmt.to_dict()
        ids = d.get("identifiers", {})
        csv_rows.append({
            "canonical_id": d["canonical_id"],
            "preferred_name": d["preferred_name"],
            "category": d.get("category") or "",
            "extensions": ";".join(ids.get("extension", [])),
            "mime_types": ";".join(ids.get("mime", [])),
            "puids": ";".join(ids.get("puid", [])),
            "loc_ids": ";".join(ids.get("loc", [])),
            "nara_ids": ";".join(ids.get("nara", [])),
            "has_qnl_policy": "yes" if d.get("qnl_policy_overlay") else "no",
            "source_count": len(d.get("source_records", [])),
        })
    write_csv(outdir / "registry.csv", csv_rows, [
        "canonical_id", "preferred_name", "category", "extensions", "mime_types", "puids", "loc_ids", "nara_ids", "has_qnl_policy", "source_count"
    ])

    write_sqlite(outdir / "registry.sqlite", registry)

    report = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "config_path": str(config_path),
        "sources": source_summaries,
        "raw_records": len(raw_records),
        "canonical_formats": len(registry),
        "qnl_policy_formats": sum(1 for x in registry if x.qnl_policy_overlay),
        "validation_errors": errors,
        "validation_warnings": warnings,
        "outputs": ["registry.json", "registry.jsonl", "registry.csv", "registry.sqlite", "source_snapshots.json", "coverage_report.md"],
    }
    write_json(outdir / "run_report.json", report)
    write_coverage_report(outdir / "coverage_report.md", registry_dicts, report)
    return report


def write_coverage_report(path: str | Path, registry: list[dict[str, Any]], report: dict[str, Any]) -> None:
    qnl = [r for r in registry if r.get("qnl_policy_overlay")]
    no_qnl = [r for r in registry if not r.get("qnl_policy_overlay")]
    missing_puid = [r for r in qnl if not r.get("identifiers", {}).get("puid")]
    missing_loc = [r for r in qnl if not r.get("identifiers", {}).get("loc")]
    lines = [
        "# Registry Build Report",
        "",
        f"Run finished: {report['finished_at']}",
        "",
        "## Summary",
        "",
        f"- Raw source records extracted: {report['raw_records']}",
        f"- Canonical formats generated: {report['canonical_formats']}",
        f"- Canonical formats with QNL policy overlay: {len(qnl)}",
        f"- Canonical formats without QNL policy overlay: {len(no_qnl)}",
        f"- QNL policy formats missing PUID: {len(missing_puid)}",
        f"- QNL policy formats missing LOC identifier: {len(missing_loc)}",
        "",
        "## Source runs",
        "",
    ]
    for src in report.get("sources", []):
        if not src.get("enabled", True):
            lines.append(f"- {src.get('source_id')}: disabled")
        else:
            lines.append(f"- {src.get('source_id')}: {src.get('records_extracted')} records from {src.get('snapshots')} snapshot(s)")
    lines.extend(["", "## Validation", ""])
    if report.get("validation_errors"):
        lines.append("### Errors")
        lines.extend(f"- {e}" for e in report["validation_errors"])
    else:
        lines.append("- No validation errors.")
    if report.get("validation_warnings"):
        lines.append("\n### Warnings")
        lines.extend(f"- {w}" for w in report["validation_warnings"])
    else:
        lines.append("- No validation warnings.")
    lines.extend(["", "## QNL policy records missing PUID", ""])
    if missing_puid:
        for r in missing_puid[:50]:
            lines.append(f"- {r['preferred_name']} ({r['canonical_id']})")
        if len(missing_puid) > 50:
            lines.append(f"- ... plus {len(missing_puid) - 50} more")
    else:
        lines.append("- None.")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
