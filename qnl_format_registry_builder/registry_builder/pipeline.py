from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from registry_builder.adapters import ADAPTERS
from registry_builder.db import write_sqlite
from registry_builder.method_profiles import assign_method_profiles, load_method_profile_config
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile
from registry_builder.utils import ensure_dir, write_csv, write_json, write_jsonl
from registry_builder.validate import validate_registry

_NON_DISCRIMINATING_METHOD_PROFILES = {"generic_preservation"}


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_config_path(config_path: str | Path, candidate: str | Path) -> Path:
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        return candidate_path
    return Path(config_path).parent / candidate_path


def maybe_assign_method_profiles(registry, config: dict[str, Any], config_path: str | Path):
    method_config = config.get("method_profiles") or {}
    if not method_config.get("enabled", False):
        return registry, None
    path = method_config.get("path")
    if not path:
        raise ValueError("method_profiles.enabled is true but no method_profiles.path was supplied")
    profile_config = load_method_profile_config(resolve_config_path(config_path, path))
    return assign_method_profiles(registry, profile_config), profile_config.get("version")


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _discriminating(profile_ids: list[str]) -> list[str]:
    return [x for x in profile_ids if x not in _NON_DISCRIMINATING_METHOD_PROFILES]


def _method_profile_metrics(registry) -> dict[str, Any]:
    direct_profile_lists = [
        _discriminating(fmt.preservation_method.get("direct_profile_ids", []))
        for fmt in registry
    ]
    effective_profile_lists = [
        _discriminating(fmt.preservation_method.get("assigned_profile_ids", []))
        for fmt in registry
    ]
    direct_counts = [len(x) for x in direct_profile_lists]
    effective_counts = [len(x) for x in effective_profile_lists]
    direct_distribution = Counter(profile_id for ids in direct_profile_lists for profile_id in ids)
    effective_distribution = Counter(profile_id for ids in effective_profile_lists for profile_id in ids)
    generic_count = sum(
        1
        for fmt in registry
        if "generic_preservation" in fmt.preservation_method.get("assigned_profile_ids", [])
    )
    metrics = {
        "formats_with_method_profiles": sum(1 for count in effective_counts if count > 0),
        "non_discriminating_method_profiles": sorted(_NON_DISCRIMINATING_METHOD_PROFILES),
        "generic_preservation_count": generic_count,
        "average_direct_discriminating_method_profiles_per_format": _average(direct_counts),
        "average_effective_discriminating_method_profiles_per_format": _average(effective_counts),
        "max_direct_discriminating_method_profiles_per_format": max(direct_counts, default=0),
        "max_effective_discriminating_method_profiles_per_format": max(effective_counts, default=0),
        "direct_method_profile_distribution": dict(sorted(direct_distribution.items())),
        "effective_method_profile_distribution": dict(sorted(effective_distribution.items())),
    }
    # Backwards-compatible aliases. These now intentionally mean discriminating
    # profiles only; `generic_preservation` is tracked separately above.
    metrics["average_direct_method_profiles_per_format"] = metrics[
        "average_direct_discriminating_method_profiles_per_format"
    ]
    metrics["average_effective_method_profiles_per_format"] = metrics[
        "average_effective_discriminating_method_profiles_per_format"
    ]
    metrics["max_direct_method_profiles_per_format"] = metrics[
        "max_direct_discriminating_method_profiles_per_format"
    ]
    metrics["max_effective_method_profiles_per_format"] = metrics[
        "max_effective_discriminating_method_profiles_per_format"
    ]
    return metrics


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
    registry, method_profile_version = maybe_assign_method_profiles(registry, config, config_path)
    errors, warnings = validate_registry(registry)
    method_metrics = _method_profile_metrics(registry)

    registry_dicts = [fmt.to_dict() for fmt in registry]
    write_jsonl(outdir / "registry.jsonl", registry_dicts)
    write_json(outdir / "registry.json", registry_dicts)
    write_jsonl(outdir / "raw_records.jsonl", [r.to_dict() for r in raw_records])
    write_json(outdir / "source_snapshots.json", [s.__dict__ for s in all_snapshots])

    csv_rows = []
    for fmt in registry:
        d = fmt.to_dict()
        ids = d.get("identifiers", {})
        method = d.get("preservation_method", {}) or {}
        csv_rows.append({
            "canonical_id": d["canonical_id"],
            "preferred_name": d["preferred_name"],
            "category": d.get("category") or "",
            "extensions": ";".join(ids.get("extension", [])),
            "mime_types": ";".join(ids.get("mime", [])),
            "puids": ";".join(ids.get("puid", [])),
            "loc_ids": ";".join(ids.get("loc", [])),
            "nara_ids": ";".join(ids.get("nara", [])),
            "has_institution_policy": "yes" if d.get("institution_policy_overlays") else "no",
            "direct_method_profiles": ";".join(method.get("direct_profile_ids", [])),
            "method_profiles": ";".join(method.get("assigned_profile_ids", [])),
            "source_count": len(d.get("source_records", [])),
        })
    write_csv(outdir / "registry.csv", csv_rows, [
        "canonical_id", "preferred_name", "category", "extensions", "mime_types", "puids", "loc_ids", "nara_ids", "has_institution_policy", "direct_method_profiles", "method_profiles", "source_count"
    ])

    write_sqlite(outdir / "registry.sqlite", registry)

    report = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "config_path": str(config_path),
        "sources": source_summaries,
        "raw_records": len(raw_records),
        "canonical_formats": len(registry),
        "institution_policy_formats": sum(1 for x in registry if x.institution_policy_overlays),
        "method_profiles_enabled": bool(config.get("method_profiles", {}).get("enabled", False)),
        "method_profile_version": method_profile_version,
        **method_metrics,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "outputs": ["registry.json", "registry.jsonl", "registry.csv", "registry.sqlite", "source_snapshots.json", "coverage_report.md"],
    }
    write_json(outdir / "run_report.json", report)
    write_coverage_report(outdir / "coverage_report.md", registry_dicts, report)
    return report


def write_coverage_report(path: str | Path, registry: list[dict[str, Any]], report: dict[str, Any]) -> None:
    institutional = [r for r in registry if r.get("institution_policy_overlays")]
    no_institutional = [r for r in registry if not r.get("institution_policy_overlays")]
    missing_puid = [r for r in institutional if not r.get("identifiers", {}).get("puid")]
    missing_loc = [r for r in institutional if not r.get("identifiers", {}).get("loc")]
    with_methods = [r for r in registry if (r.get("preservation_method") or {}).get("assigned_profile_ids")]
    lines = [
        "# Registry Build Report",
        "",
        f"Run finished: {report['finished_at']}",
        "",
        "## Summary",
        "",
        f"- Raw source records extracted: {report['raw_records']}",
        f"- Canonical formats generated: {report['canonical_formats']}",
        f"- Canonical formats with institutional policy overlay: {len(institutional)}",
        f"- Canonical formats without institutional policy overlay: {len(no_institutional)}",
        f"- Institutional policy formats missing PUID: {len(missing_puid)}",
        f"- Institutional policy formats missing LOC identifier: {len(missing_loc)}",
        f"- Canonical formats with preservation method profiles: {len(with_methods)}",
        f"- Generic preservation baseline count: {report.get('generic_preservation_count', 0)}",
        f"- Average direct discriminating method profiles per format: {report.get('average_direct_discriminating_method_profiles_per_format', 0)}",
        f"- Average effective discriminating method profiles per format: {report.get('average_effective_discriminating_method_profiles_per_format', 0)}",
        "",
        "## Method profile distribution",
        "",
    ]
    direct_distribution = report.get("direct_method_profile_distribution", {}) or {}
    if direct_distribution:
        lines.append("### Direct profiles")
        lines.extend(f"- {profile}: {count}" for profile, count in direct_distribution.items())
    else:
        lines.append("- No direct method profiles assigned.")
    effective_distribution = report.get("effective_method_profile_distribution", {}) or {}
    if effective_distribution:
        lines.append("\n### Effective profiles, excluding generic baseline")
        lines.extend(f"- {profile}: {count}" for profile, count in effective_distribution.items())
    lines.extend(["", "## Source runs", ""])
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
    lines.extend(["", "## Institutional policy records missing PUID", ""])
    if missing_puid:
        for r in missing_puid[:50]:
            lines.append(f"- {r['preferred_name']} ({r['canonical_id']})")
        if len(missing_puid) > 50:
            lines.append(f"- ... plus {len(missing_puid) - 50} more")
    else:
        lines.append("- None.")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
