from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from registry_builder.adapters import resolve_adapter
from registry_builder.change_detection import compact_change_summary, detect_registry_changes
from registry_builder.db import write_sqlite
from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.method_profiles import assign_method_profiles, load_method_profile_config
from registry_builder.models import CanonicalFormat, Identifier, RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore
from registry_builder.utils import ensure_dir, write_csv, write_json, write_jsonl
from registry_builder.validate import summarize_validation_warnings, validate_registry, validation_warning_counts

_NON_DISCRIMINATING_METHOD_PROFILES = {"generic_preservation"}
_RAW_RECORD_FIELD_NAMES = set(RawFormatRecord.__dataclass_fields__)


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


def _new_run_id() -> str:
    return f"run-{utc_now_iso().replace(':', '').replace('+', 'Z')}-{uuid4().hex[:8]}"


def _exports_enabled(config: dict[str, Any]) -> bool:
    exports = config.get("exports")
    if exports is None:
        return True
    if isinstance(exports, bool):
        return exports
    if isinstance(exports, dict):
        return bool(exports.get("enabled", True))
    if isinstance(exports, list):
        return any(bool(item.get("enabled", True)) for item in exports)
    return bool(exports)


def _incremental_source_updates_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("incremental_source_updates", True))


def _storage_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("storage") or {"type": "memory"})


def _source_required(source: dict[str, Any]) -> bool:
    return bool(source.get("required", True))


def _snapshot_dict(snapshot: SourceSnapshot, run_id: str) -> dict[str, Any]:
    data = snapshot.__dict__.copy()
    data["run_id"] = run_id
    return data


def _source_record_dict(record: RawFormatRecord, run_id: str) -> dict[str, Any]:
    data = record.to_dict()
    data["run_id"] = run_id
    return data


def _identifier_from_dict(value: Identifier | dict[str, Any]) -> Identifier:
    if isinstance(value, Identifier):
        return value
    return Identifier(
        kind=str(value.get("kind") or value.get("type") or ""),
        value=str(value.get("value") or ""),
        source=str(value.get("source") or ""),
        verified=bool(value.get("verified", False)),
        source_record_id=value.get("source_record_id"),
    )


def _raw_record_from_dict(data: dict[str, Any]) -> RawFormatRecord:
    payload = {key: data[key] for key in _RAW_RECORD_FIELD_NAMES if key in data}
    payload["identifiers"] = [_identifier_from_dict(item) for item in payload.get("identifiers", [])]
    return RawFormatRecord(**payload)


def _run_timestamp_index(store: RegistryStore) -> dict[str, str]:
    index: dict[str, str] = {}
    for run in store.query("runs"):
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        index[run_id] = str(run.get("finished_at") or run.get("started_at") or run_id)
    return index


def _latest_stored_source_records(
    store: RegistryStore,
    *,
    refreshed_source_ids: set[str],
    identifier_rules: dict[str, dict[str, Any]],
) -> list[RawFormatRecord]:
    """Return latest stored source records for sources not refreshed this run.

    Source-by-source registry population works by replacing only the evidence for
    sources that completed in the current run, then rebuilding canonical formats
    from current-run records plus latest stored records from all other sources.
    A failed optional source is not considered refreshed, so its last successful
    evidence remains active.
    """
    run_index = _run_timestamp_index(store)
    latest: dict[tuple[str, str], tuple[tuple[str, str], dict[str, Any]]] = {}
    for record in store.query("source_records"):
        source_id = str(record.get("source_id") or "")
        if not source_id or source_id in refreshed_source_ids:
            continue
        source_record_id = str(
            record.get("source_record_id")
            or record.get("_storage_key")
            or record.get("_file_storage_key")
            or ""
        )
        if not source_record_id:
            continue
        run_id = str(record.get("run_id") or "")
        sort_key = (run_index.get(run_id, run_id), run_id)
        key = (source_id, source_record_id)
        if key not in latest or sort_key > latest[key][0]:
            latest[key] = (sort_key, record)

    restored: list[RawFormatRecord] = []
    for _, record in latest.values():
        restored.append(normalize_record(_raw_record_from_dict(record), identifier_rules=identifier_rules))
    return restored


def _source_snapshot_status(snapshots: list[SourceSnapshot], *, offline: bool) -> dict[str, Any]:
    changed = sum(1 for snapshot in snapshots if snapshot.changed is True)
    unchanged = sum(1 for snapshot in snapshots if snapshot.changed is False and not snapshot.from_cache)
    from_cache = sum(1 for snapshot in snapshots if snapshot.from_cache)
    unknown = sum(1 for snapshot in snapshots if snapshot.changed is None)
    return {
        "offline": offline,
        "source_changed": changed > 0,
        "snapshots_changed": changed,
        "snapshots_unchanged": unchanged,
        "snapshots_from_cache": from_cache,
        "snapshots_unknown": unknown,
    }


def _empty_source_status(*, offline: bool) -> dict[str, Any]:
    return {
        "offline": offline,
        "source_changed": False,
        "snapshots_changed": 0,
        "snapshots_unchanged": 0,
        "snapshots_from_cache": 0,
        "snapshots_unknown": 0,
    }


def _persist_registry_to_store(
    store: RegistryStore,
    *,
    run_id: str,
    snapshots: list[SourceSnapshot],
    raw_records: list[RawFormatRecord],
    registry: list[CanonicalFormat],
    previous_registry: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
) -> None:
    """Persist the build directly to the selected RegistryStore.

    This is not a JSON staging step. The pipeline persists the in-memory objects
    it has already produced. Export files, when enabled, are generated later and
    are optional review/interchange products.
    """
    previous_registry = previous_registry or []
    changes = changes or []
    current_ids: set[str] = set()
    removed_at = utc_now_iso()

    for snapshot in snapshots:
        store.save_snapshot(_snapshot_dict(snapshot, run_id))

    for record in raw_records:
        store.save_source_record(_source_record_dict(record, run_id))

    for fmt in registry:
        fmt_dict = fmt.to_dict()
        canonical_id = fmt_dict["canonical_id"]
        current_ids.add(canonical_id)
        stored_format = fmt_dict | {
            "run_id": run_id,
            "format_id": canonical_id,
            "current": True,
            "last_seen_run_id": run_id,
        }
        store.upsert_canonical_format(stored_format)

        for claim in fmt_dict.get("identifier_claims", []):
            store.upsert_identifier({
                "run_id": run_id,
                "format_id": canonical_id,
                "canonical_id": canonical_id,
                "type": claim.get("kind"),
                "value": claim.get("value"),
                "source": claim.get("source"),
                "verified": claim.get("verified", False),
                "source_record_id": claim.get("source_record_id"),
            })

        for overlay in fmt_dict.get("institution_policy_overlays", []):
            store.save_institution_policy_overlay(
                overlay | {"run_id": run_id, "format_id": canonical_id, "canonical_id": canonical_id}
            )

        hazard = fmt_dict.get("hazard_assessment") or {}
        if hazard:
            store.save_hazard_assessment(
                hazard | {"run_id": run_id, "format_id": canonical_id, "canonical_id": canonical_id}
            )

        for sequence, readiness in enumerate(fmt_dict.get("readiness", []), start=1):
            store.save_readiness_assessment(
                readiness | {"run_id": run_id, "format_id": canonical_id, "canonical_id": canonical_id, "sequence": sequence}
            )

        for sequence, trend in enumerate(fmt_dict.get("trend", []), start=1):
            store.save_trend_observation(
                trend | {"run_id": run_id, "format_id": canonical_id, "canonical_id": canonical_id, "sequence": sequence}
            )

    for previous in previous_registry:
        canonical_id = str(previous.get("canonical_id") or "")
        if canonical_id and canonical_id not in current_ids:
            removed = previous | {
                "canonical_id": canonical_id,
                "format_id": canonical_id,
                "current": False,
                "last_removed_run_id": run_id,
                "removed_at": removed_at,
            }
            store.upsert_canonical_format(removed)

    for change in changes:
        store.save_assessment_change(change)


def _write_file_exports(
    outdir: Path,
    registry: list[CanonicalFormat],
    active_source_records: list[RawFormatRecord],
    snapshots: list[SourceSnapshot],
    report: dict[str, Any],
) -> list[str]:
    registry_dicts = [fmt.to_dict() for fmt in registry]
    write_jsonl(outdir / "registry.jsonl", registry_dicts)
    write_json(outdir / "registry.json", registry_dicts)
    write_jsonl(outdir / "raw_records.jsonl", [r.to_dict() for r in active_source_records])
    write_json(outdir / "source_snapshots.json", [s.__dict__ for s in snapshots])

    csv_rows = []
    for fmt in registry:
        d = fmt.to_dict()
        ids = d.get("identifiers", {})
        method = d.get("preservation_method", {}) or {}
        hazard = d.get("hazard_assessment", {}) or {}
        csv_rows.append({
            "canonical_id": d["canonical_id"],
            "preferred_name": d["preferred_name"],
            "category": d.get("category") or "",
            "extensions": ";".join(ids.get("extension", [])),
            "mime_types": ";".join(ids.get("mime", [])),
            "puids": ";".join(ids.get("puid", [])),
            "loc_ids": ";".join(ids.get("loc", [])),
            "nara_ids": ";".join(ids.get("nara", [])),
            "hazard_basis": hazard.get("basis", ""),
            "hazard_band": hazard.get("band", ""),
            "external_rating_native": hazard.get("external_rating_native", ""),
            "external_rating_native_direction": hazard.get("external_rating_native_direction", ""),
            "has_institution_policy": "yes" if d.get("institution_policy_overlays") else "no",
            "direct_method_profiles": ";".join(method.get("direct_profile_ids", [])),
            "method_profiles": ";".join(method.get("assigned_profile_ids", [])),
            "source_count": len(d.get("source_records", [])),
        })
    write_csv(outdir / "registry.csv", csv_rows, [
        "canonical_id", "preferred_name", "category", "extensions", "mime_types", "puids", "loc_ids", "nara_ids", "hazard_basis", "hazard_band", "external_rating_native", "external_rating_native_direction", "has_institution_policy", "direct_method_profiles", "method_profiles", "source_count"
    ])

    write_sqlite(outdir / "registry.sqlite", registry)
    write_json(outdir / "run_report.json", report)
    write_coverage_report(outdir / "coverage_report.md", registry_dicts, report)
    return [
        "registry.json",
        "registry.jsonl",
        "registry.csv",
        "registry.sqlite",
        "raw_records.jsonl",
        "source_snapshots.json",
        "run_report.json",
        "coverage_report.md",
    ]


def run_pipeline(config_path: str | Path, workdir: str | Path, outdir: str | Path, *, offline: bool = False) -> dict[str, Any]:
    started_at = utc_now_iso()
    run_id = _new_run_id()
    config = load_config(config_path)
    offline = bool(offline or config.get("offline", False))
    incremental_source_updates = _incremental_source_updates_enabled(config)
    identifier_rules = load_identifier_rules(config.get("identifier_kinds"))
    workdir = ensure_dir(workdir)
    outdir = ensure_dir(outdir)
    storage_config = _storage_config(config)
    store = create_store(storage_config)
    previous_registry_view = store.get_current_registry_view()
    store.create_run({
        "run_id": run_id,
        "started_at": started_at,
        "status": "running",
        "config_path": str(config_path),
        "storage": storage_config,
        "offline": offline,
        "incremental_source_updates": incremental_source_updates,
        "previous_canonical_formats": len(previous_registry_view),
    })

    all_snapshots: list[SourceSnapshot] = []
    raw_records: list[RawFormatRecord] = []
    source_summaries: list[dict[str, Any]] = []

    for source in config.get("sources", []):
        required = _source_required(source)
        if not source.get("enabled", True):
            source_summaries.append({
                "source_id": source.get("id"),
                "enabled": False,
                "required": required,
                "status": "disabled",
                "snapshots": 0,
                "records_extracted": 0,
                **_empty_source_status(offline=offline),
            })
            continue

        try:
            source_type = source["type"]
            adapter_cls = resolve_adapter(source_type)
            source_config = dict(source)
            if offline:
                source_config["offline"] = True
            adapter = adapter_cls(source_config, workdir)
            snapshots = adapter.acquire()
            extracted = adapter.extract(snapshots)
            all_snapshots.extend(snapshots)
            raw_records.extend(normalize_record(r, identifier_rules=identifier_rules) for r in extracted)
            source_summaries.append({
                "source_id": source["id"],
                "source_type": source_type,
                "enabled": True,
                "required": required,
                "status": "completed",
                "snapshots": len(snapshots),
                "records_extracted": len(extracted),
                **_source_snapshot_status(snapshots, offline=offline),
            })
        except Exception as exc:
            failed = {
                "source_id": source.get("id"),
                "source_type": source.get("type"),
                "enabled": True,
                "required": required,
                "status": "failed",
                "snapshots": 0,
                "records_extracted": 0,
                "error_type": type(exc).__name__,
                "error": str(exc),
                **_empty_source_status(offline=offline),
            }
            source_summaries.append(failed)
            if required:
                raise
            continue

    completed_source_ids = {
        str(s.get("source_id"))
        for s in source_summaries
        if s.get("enabled", True) and s.get("status") == "completed" and s.get("source_id")
    }
    prior_source_records = (
        _latest_stored_source_records(
            store,
            refreshed_source_ids=completed_source_ids,
            identifier_rules=identifier_rules,
        )
        if incremental_source_updates
        else []
    )
    active_source_records = prior_source_records + raw_records

    registry = reconcile(active_source_records, identifier_rules=identifier_rules)
    registry, method_profile_version = maybe_assign_method_profiles(registry, config, config_path)
    errors, warnings = validate_registry(registry)
    warning_summary = summarize_validation_warnings(warnings)
    warning_counts = validation_warning_counts(warnings)
    method_metrics = _method_profile_metrics(registry)
    registry_dicts = [fmt.to_dict() for fmt in registry]
    change_detection = detect_registry_changes(
        previous_registry_view,
        registry_dicts,
        run_id=run_id,
        created_at=utc_now_iso(),
    )
    change_summary = compact_change_summary(change_detection)

    _persist_registry_to_store(
        store,
        run_id=run_id,
        snapshots=all_snapshots,
        raw_records=raw_records,
        registry=registry,
        previous_registry=previous_registry_view,
        changes=change_detection.get("changes", []),
    )

    enabled_sources = [s for s in source_summaries if s.get("enabled", True)]
    completed_sources = [s for s in enabled_sources if s.get("status") == "completed"]
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "status": "completed",
        "config_path": str(config_path),
        "offline": offline,
        "incremental_source_updates": incremental_source_updates,
        "storage": {
            "type": storage_config.get("type", "memory"),
            "path": storage_config.get("path") or storage_config.get("directory") or storage_config.get("root"),
            "database": storage_config.get("database") or storage_config.get("db"),
            "collection_prefix": storage_config.get("collection_prefix"),
        },
        "sources": source_summaries,
        "identifier_kinds": identifier_rules,
        "source_status_counts": dict(Counter(s.get("status", "unknown") for s in source_summaries)),
        "source_change_counts": dict(Counter("changed" if s.get("source_changed") else "unchanged" for s in completed_sources)),
        "raw_records": len(active_source_records),
        "raw_records_extracted": len(raw_records),
        "prior_source_records_reused": len(prior_source_records),
        "active_source_records": len(active_source_records),
        "refreshed_source_ids": sorted(completed_source_ids),
        "canonical_formats": len(registry),
        "institution_policy_formats": sum(1 for x in registry if x.institution_policy_overlays),
        "method_profiles_enabled": bool(config.get("method_profiles", {}).get("enabled", False)),
        "method_profile_version": method_profile_version,
        **method_metrics,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "validation_warning_counts": warning_counts,
        "validation_warning_summary": warning_summary,
        "change_detection": change_summary,
        "change_counts": change_summary.get("change_counts", {}),
        "changes": change_summary.get("sample_changes", []),
        "exports_enabled": _exports_enabled(config),
        "outputs": [],
    }

    if _exports_enabled(config):
        report["outputs"] = _write_file_exports(outdir, registry, active_source_records, all_snapshots, report)

    store.create_run(report)
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
        f"Run ID: {report.get('run_id')}",
        f"Run finished: {report['finished_at']}",
        "",
        "## Summary",
        "",
        f"- Storage backend: {report.get('storage', {}).get('type')}",
        f"- Offline mode: {report.get('offline', False)}",
        f"- Incremental source updates: {report.get('incremental_source_updates', True)}",
        f"- Raw source records extracted this run: {report.get('raw_records_extracted', report.get('raw_records', 0))}",
        f"- Prior source records reused: {report.get('prior_source_records_reused', 0)}",
        f"- Active source records used for reconciliation: {report.get('active_source_records', report.get('raw_records', 0))}",
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
        "## Source runs",
        "",
    ]
    for src in report.get("sources", []):
        if not src.get("enabled", True):
            lines.append(f"- {src.get('source_id')}: disabled")
        elif src.get("status") == "failed":
            lines.append(
                f"- {src.get('source_id')}: failed; required={src.get('required')}; "
                f"{src.get('error_type')}: {src.get('error')}"
            )
        else:
            status = "changed" if src.get("source_changed") else "unchanged"
            lines.append(
                f"- {src.get('source_id')}: {src.get('records_extracted')} records from {src.get('snapshots')} snapshot(s); "
                f"{status}; changed={src.get('snapshots_changed', 0)}, unchanged={src.get('snapshots_unchanged', 0)}, cached={src.get('snapshots_from_cache', 0)}"
            )

    lines.extend(["", "## Change detection", ""])
    change_detection = report.get("change_detection") or {}
    lines.append(f"- Run kind: {change_detection.get('run_kind')}")
    if change_detection.get("baseline_note"):
        lines.append(f"- {change_detection.get('baseline_note')}")
    lines.append(f"- Total actionable changes: {change_detection.get('total_changes', 0)}")
    if change_detection.get("change_counts"):
        lines.append("- Change counts:")
        lines.extend(f"  - {k}: {v}" for k, v in change_detection.get("change_counts", {}).items())
    if change_detection.get("raw_change_counts"):
        lines.append("- Raw change counts before bulk collapse:")
        lines.extend(f"  - {k}: {v}" for k, v in change_detection.get("raw_change_counts", {}).items())
    if change_detection.get("bulk_changes"):
        lines.append("- Bulk-collapsed changes:")
        for item in change_detection.get("bulk_changes", []):
            lines.append(
                f"  - {item.get('collapsed_change_type')}: {item.get('affected_count')} records collapsed into source_coverage_changed"
            )

    lines.extend(["", "## Method profile distribution", ""])
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

    lines.extend(["", "## Validation", ""])
    if report.get("validation_errors"):
        lines.append("### Errors")
        lines.extend(f"- {e}" for e in report["validation_errors"])
    else:
        lines.append("- No validation errors.")

    warning_summary = report.get("validation_warning_summary") or {}
    if warning_summary:
        lines.append("\n### Warning summary")
        for warning_type, info in warning_summary.items():
            lines.append(f"- {warning_type}: {info.get('count', 0)}")
            for sample in info.get("samples", [])[:3]:
                lines.append(f"  - sample: {sample}")
    else:
        lines.append("- No validation warnings.")

    warnings = report.get("validation_warnings") or []
    if warnings:
        lines.append("\n### Warning detail, first 50")
        lines.extend(f"- {w}" for w in warnings[:50])
        if len(warnings) > 50:
            lines.append(f"- ... plus {len(warnings) - 50} more warnings; see run_report.json for full detail.")

    lines.extend(["", "## Institutional policy records missing PUID", ""])
    if missing_puid:
        for r in missing_puid[:50]:
            lines.append(f"- {r['preferred_name']} ({r['canonical_id']})")
        if len(missing_puid) > 50:
            lines.append(f"- ... plus {len(missing_puid) - 50} more")
    else:
        lines.append("- None.")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
