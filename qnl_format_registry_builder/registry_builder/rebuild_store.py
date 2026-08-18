from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from registry_builder.change_detection import compact_change_summary, detect_registry_changes
from registry_builder.criterion_mapping import build_criterion_claims
from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.pipeline import (
    _criterion_claim_summary,
    _exports_enabled,
    _load_criterion_mapping_inputs,
    _method_profile_metrics,
    _new_run_id,
    _persist_registry_to_store,
    _storage_config,
    _stored_source_records_for_augmentation,
    _write_file_exports,
    load_config,
    maybe_assign_method_profiles,
)
from registry_builder.reconcile import reconcile
from registry_builder.storage import create_store
from registry_builder.utils import ensure_dir
from registry_builder.validate import summarize_validation_warnings, validate_registry, validation_warning_counts
from registry_builder.models import utc_now_iso


def _stored_source_summaries(records) -> list[dict[str, Any]]:
    counts = Counter((str(record.source_id or ""), str(record.source_type or "")) for record in records)
    rows: list[dict[str, Any]] = []
    for (source_id, source_type), count in sorted(counts.items()):
        rows.append({
            "source_id": source_id,
            "source_type": source_type,
            "enabled": True,
            "required": None,
            # Deliberately not "completed": _latest_completed_source_run_index()
            # must continue to point at the last real acquisition run, because
            # rebuild-from-store does not create new source-record snapshots.
            "status": "reused_from_store",
            "snapshots": 0,
            "records_extracted": count,
            "stored_records_reused": count,
        })
    return rows


def rebuild_registry_from_store(config_path: str | Path, outdir: str | Path) -> dict[str, Any]:
    """Rebuild canonical formats and criterion claims from stored source records.

    This performs no network/source acquisition. It reuses the latest completed
    source-record set already held by the configured RegistryStore, then reruns
    normalization, reconciliation, validation, method-profile assignment,
    criterion mapping, change detection, and canonical/claim persistence.

    Source records and source snapshots themselves are not rewritten. This keeps
    the last real acquisition run authoritative for future incremental source
    augmentation.
    """
    config_path = Path(config_path)
    outdir = ensure_dir(outdir)
    config = load_config(config_path)
    storage_config = _storage_config(config)
    if str(storage_config.get("type") or "memory").lower() == "memory":
        raise ValueError("rebuild-from-store requires a persistent RegistryStore configuration, not memory storage")

    store = create_store(storage_config)
    previous_registry = store.get_current_registry_view()
    identifier_rules = load_identifier_rules(config.get("identifier_kinds"))

    source_records = _stored_source_records_for_augmentation(
        store,
        current_run_source_ids=set(),
        identifier_rules=identifier_rules,
    )
    if not source_records:
        raise ValueError("No stored source records were found. Run the normal acquisition pipeline first.")

    registry = reconcile(source_records, identifier_rules=identifier_rules)
    registry, method_profile_version = maybe_assign_method_profiles(registry, config, config_path)
    errors, warnings = validate_registry(registry)
    if errors:
        raise ValueError(
            "Rebuilt registry failed validation and was not persisted: " + "; ".join(errors[:20])
        )

    source_summaries = _stored_source_summaries(source_records)
    criterion_mapping_inputs = _load_criterion_mapping_inputs(config, config_path)
    criterion_claims: list[dict[str, Any]] = []
    criterion_mapping_report: dict[str, Any] = {"enabled": False, "claims_generated": 0}
    registry_dicts = [fmt.to_dict() for fmt in registry]
    if criterion_mapping_inputs is not None:
        criteria, mappings, criterion_mapping_report = criterion_mapping_inputs
        source_record_dicts = [record.to_dict() for record in source_records]
        criterion_claims = build_criterion_claims(
            registry_dicts,
            source_record_dicts,
            mappings,
            criteria,
            include_drafts=criterion_mapping_report.get("include_drafts", False),
        )
        criterion_mapping_report = criterion_mapping_report | _criterion_claim_summary(
            criterion_claims,
            source_summaries=source_summaries,
            mappings=mappings,
        )

    run_id = _new_run_id()
    started_at = utc_now_iso()
    change_detection = detect_registry_changes(
        previous_registry,
        registry_dicts,
        run_id=run_id,
        created_at=started_at,
    )
    change_summary = compact_change_summary(change_detection)
    warning_summary = summarize_validation_warnings(warnings)
    warning_counts = validation_warning_counts(warnings)
    method_metrics = _method_profile_metrics(registry)

    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "status": "completed",
        "run_kind": "rebuild_from_store",
        "rebuild_from_store": True,
        "config_path": str(config_path),
        "offline": True,
        "incremental_source_updates": bool(config.get("incremental_source_updates", True)),
        "criterion_mapping": criterion_mapping_report,
        "storage": {
            "type": storage_config.get("type"),
            "path": storage_config.get("path") or storage_config.get("directory") or storage_config.get("root"),
            "database": storage_config.get("database") or storage_config.get("db"),
            "collection_prefix": storage_config.get("collection_prefix"),
        },
        "sources": source_summaries,
        "identifier_kinds": identifier_rules,
        "source_status_counts": {"reused_from_store": len(source_summaries)},
        "stored_source_records_reused": len(source_records),
        "active_source_records": len(source_records),
        "canonical_formats": len(registry),
        "previous_canonical_formats": len(previous_registry),
        "institution_policy_formats": sum(1 for item in registry if item.institution_policy_overlays),
        "method_profiles_enabled": bool(config.get("method_profiles", {}).get("enabled", False)),
        "method_profile_version": method_profile_version,
        **method_metrics,
        "validation_errors": [],
        "validation_warnings": warnings,
        "validation_warning_counts": warning_counts,
        "validation_warning_summary": warning_summary,
        "change_detection": change_summary,
        "change_counts": change_summary.get("change_counts", {}),
        "changes": change_summary.get("sample_changes", []),
        "exports_enabled": _exports_enabled(config),
        "outputs": [],
    }

    # Persist only rebuilt canonical/claim/change state. Stored source records
    # were acquired previously and must not be duplicated under this rebuild run.
    _persist_registry_to_store(
        store,
        run_id=run_id,
        snapshots=[],
        raw_records=[],
        registry=registry,
        criterion_claims=criterion_claims,
        previous_registry=previous_registry,
        changes=change_detection.get("changes", []),
    )

    if _exports_enabled(config):
        report["outputs"] = _write_file_exports(
            outdir,
            registry,
            source_records,
            [],
            report,
            criterion_claims if criterion_mapping_inputs is not None else None,
        )

    store.create_run(report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.rebuild_store",
        description="Rebuild canonical formats and criterion claims from source records already stored in the registry database.",
    )
    parser.add_argument("--config", required=True, help="Pipeline config containing persistent storage, identifier, mapping, and method-profile settings.")
    parser.add_argument("--out", default="output-rebuild", help="Output directory for rebuilt exports/report. Default: output-rebuild")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = rebuild_registry_from_store(args.config, args.out)
    print(f"Rebuild complete: {report['canonical_formats']} canonical formats")
    print(f"Stored source records reused: {report['stored_source_records_reused']}")
    print(f"Criterion claims generated: {report['criterion_mapping'].get('claims_generated', 0)}")
    print(f"Validation warnings: {len(report['validation_warnings'])}")
    print(f"Changes detected: {report['change_detection'].get('total_changes', 0)}")
    print(f"Output directory: {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
