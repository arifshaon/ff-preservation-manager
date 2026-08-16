from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from registry_builder.collision_report import build_collision_report
from registry_builder.criteria import load_criteria
from registry_builder.criterion_evidence_audit import run_criterion_evidence_audit
from registry_builder.criterion_mapping import (
    backfill_criterion_claims,
    create_store_from_storage_config,
    load_mappings,
    validate_mappings,
)
from registry_builder.pipeline import run_pipeline
from registry_builder.storage import create_store
from registry_builder.validate import validate_registry
from registry_builder.models import CanonicalFormat


def _load_registry(path: str | Path) -> list[CanonicalFormat]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CanonicalFormat(**row) for row in rows]


def _load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must contain a JSON object: {path}")
    return data


def _resolve_relative(base: str | Path, candidate: str | Path) -> str:
    path = Path(candidate)
    if path.is_absolute():
        return str(path)
    return str(Path(base).parent / path)


def _write_or_print(result: dict, out: str | None = None) -> None:
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def _progress_enabled(args, config: dict[str, Any] | None = None) -> bool:
    if getattr(args, "no_progress", False):
        return False
    if config and "progress" in config:
        return bool(config.get("progress"))
    return True


def _progress_every(args, config: dict[str, Any] | None = None) -> int:
    value = getattr(args, "progress_every", None)
    if value is None and config:
        value = config.get("progress_every")
    return max(1, int(value or 500))


def _format_progress(event: dict[str, Any]) -> str:
    name = event.get("event")
    if name == "validate_mappings_started":
        return f"[criterion-claims] validating {event.get('mappings', 0)} mapping file(s)..."
    if name == "validate_mappings_completed":
        return f"[criterion-claims] mappings valid; warnings={event.get('warnings', 0)}"
    if name == "validate_mappings_failed":
        return f"[criterion-claims] mapping validation failed; errors={event.get('errors', 0)}"
    if name == "load_canonical_formats_started":
        return "[criterion-claims] loading current canonical formats..."
    if name == "load_canonical_formats_completed":
        return f"[criterion-claims] loaded {event.get('canonical_formats', 0)} canonical format(s)"
    if name == "load_source_records_started":
        return "[criterion-claims] loading source records..."
    if name == "load_source_records_completed":
        return f"[criterion-claims] loaded {event.get('source_records', 0)} source record(s)"
    if name == "build_claims_started":
        return (
            "[criterion-claims] building claims from "
            f"{event.get('canonical_formats', 0)} canonical format(s), "
            f"{event.get('source_records', 0)} source record(s), "
            f"{event.get('mapping_rules', 0)} mapping rule(s)..."
        )
    if name == "build_claims_progress":
        return (
            "[criterion-claims] mapped "
            f"{event.get('canonical_formats_processed', 0)}/{event.get('canonical_formats', 0)} "
            f"canonical format(s); claims={event.get('claims_generated', 0)}"
        )
    if name == "build_claims_completed":
        return f"[criterion-claims] claim build complete; claims={event.get('claims_generated', 0)}"
    if name == "dry_run_skipping_write":
        return f"[criterion-claims] dry run; skipping write of {event.get('claims', 0)} claim(s)"
    if name == "supersede_claims_started":
        return f"[criterion-claims] superseding {event.get('claims', 0)} old current claim(s)..."
    if name == "supersede_claims_progress":
        return f"[criterion-claims] superseded {event.get('claims_superseded', 0)}/{event.get('claims', 0)} old claim(s)"
    if name == "supersede_claims_completed":
        return f"[criterion-claims] supersede complete; claims_superseded={event.get('claims_superseded', 0)}"
    if name == "write_claims_started":
        return f"[criterion-claims] writing {event.get('claims', 0)} claim(s)..."
    if name == "write_claims_progress":
        return f"[criterion-claims] wrote {event.get('claims_written', 0)}/{event.get('claims', 0)} claim(s)"
    if name == "write_claims_completed":
        return f"[criterion-claims] write complete; claims_written={event.get('claims_written', 0)}"
    if name == "backfill_completed":
        return f"[criterion-claims] completed; status={event.get('status')}; claims={event.get('claims_generated', 0)}"
    return "[criterion-claims] " + json.dumps(event, ensure_ascii=False, sort_keys=True)


def _progress_reporter(enabled: bool):
    if not enabled:
        return None

    def report(event: dict[str, Any]) -> None:
        print(_format_progress(event), file=sys.stderr, flush=True)

    return report


def _backfill_inputs(args) -> tuple[Any, Any, list[dict[str, Any]], str | None, bool, bool, bool, bool, int]:
    if not args.config:
        missing = [
            name
            for name, value in (
                ("--storage-config", args.storage_config),
                ("--criteria", args.criteria),
                ("--mappings", args.mappings),
            )
            if not value
        ]
        if missing:
            raise SystemExit("criterion-claims backfill requires --config or " + ", ".join(missing))
        return (
            create_store_from_storage_config(args.storage_config),
            load_criteria(args.criteria),
            load_mappings(args.mappings),
            args.out,
            args.dry_run,
            args.include_drafts,
            args.replace_source_claims,
            _progress_enabled(args),
            _progress_every(args),
        )

    cfg = _load_json(args.config)
    storage_config = cfg.get("storage")
    if not isinstance(storage_config, dict):
        raise SystemExit("Backfill config must contain a storage object")
    criteria_path = args.criteria or cfg.get("criteria")
    mappings_path = args.mappings or cfg.get("mappings")
    if not criteria_path:
        raise SystemExit("Backfill config must contain criteria, or pass --criteria")
    if not mappings_path:
        raise SystemExit("Backfill config must contain mappings, or pass --mappings")
    out = args.out if args.out is not None else cfg.get("out")
    dry_run = bool(args.dry_run or cfg.get("dry_run", False))
    include_drafts = bool(args.include_drafts or cfg.get("include_drafts", False))
    replace_source_claims = bool(args.replace_source_claims or cfg.get("replace_source_claims", False))
    return (
        create_store(storage_config),
        load_criteria(_resolve_relative(args.config, criteria_path)),
        load_mappings(_resolve_relative(args.config, mappings_path)),
        _resolve_relative(args.config, out) if out else None,
        dry_run,
        include_drafts,
        replace_source_claims,
        _progress_enabled(args, cfg),
        _progress_every(args, cfg),
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="registry-builder")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the registry-building pipeline")
    run.add_argument("--config", required=True)
    run.add_argument("--workdir", default="work")
    run.add_argument("--out", default="out")
    run.add_argument("--offline", action="store_true", help="Use cached source snapshots only; do not fetch remote sources")

    val = sub.add_parser("validate", help="Validate a generated registry.json")
    val.add_argument("--registry", required=True)

    collision = sub.add_parser("collision-report", help="Report identifier collisions and heuristic bridges")
    collision.add_argument("--registry", required=True)
    collision.add_argument("--sample-limit", type=int, default=50)

    audit = sub.add_parser("criterion-evidence-audit", help="Read-only audit of source fields and projected criterion-claim coverage")
    audit.add_argument("--storage-config", required=True, help="Registry-builder storage block or full pipeline config containing storage")
    audit.add_argument("--criteria", help="Neutral criteria vocabulary JSON")
    audit.add_argument("--mappings", help="Mapping file or directory for projected coverage")
    audit.add_argument("--source", help="Optional source_id or source_type filter")
    audit.add_argument("--out", help="Optional JSON output file")

    mapping = sub.add_parser("mapping", help="Mapping configuration operations")
    mapping_sub = mapping.add_subparsers(dest="mapping_command", required=True)
    mapping_validate = mapping_sub.add_parser("validate", help="Validate criterion mapping config(s)")
    mapping_validate.add_argument("--criteria", required=True)
    mapping_validate.add_argument("--mappings", required=True)

    claims = sub.add_parser("criterion-claims", help="Criterion-claim collection operations")
    claims_sub = claims.add_subparsers(dest="claims_command", required=True)
    claims_backfill = claims_sub.add_parser("backfill", help="Backfill criterion_claims from existing canonical/source records")
    claims_backfill.add_argument("--config", help="Mode 2 backfill config containing storage, criteria, mappings and optional output")
    claims_backfill.add_argument("--storage-config")
    claims_backfill.add_argument("--criteria")
    claims_backfill.add_argument("--mappings")
    claims_backfill.add_argument("--dry-run", action="store_true")
    claims_backfill.add_argument("--include-drafts", action="store_true", help="Apply draft mappings too; intended for projection/debug only")
    claims_backfill.add_argument(
        "--replace-source-claims",
        action="store_true",
        help="Mark old current criterion claims from the mapped source(s) as superseded when this backfill no longer produces them.",
    )
    claims_backfill.add_argument("--out", help="Optional JSON output file")
    claims_backfill.add_argument("--progress-every", type=int, default=500, help="Report progress after this many canonical formats/claims")
    claims_backfill.add_argument("--no-progress", action="store_true", help="Suppress progress messages on stderr")

    args = parser.parse_args()

    if args.command == "run":
        report = run_pipeline(args.config, args.workdir, args.out, offline=args.offline)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "validate":
        registry = _load_registry(args.registry)
        errors, warnings = validate_registry(registry)
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
        if errors:
            raise SystemExit(1)
    elif args.command == "collision-report":
        registry = _load_registry(args.registry)
        report = build_collision_report(registry, sample_limit=args.sample_limit)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if report.get("status") == "error":
            raise SystemExit(1)
    elif args.command == "criterion-evidence-audit":
        store = create_store_from_storage_config(args.storage_config)
        criteria = load_criteria(args.criteria) if args.criteria else None
        report = run_criterion_evidence_audit(
            store,
            criteria=criteria,
            mappings_path=args.mappings,
            source=args.source,
        )
        _write_or_print(report, args.out)
    elif args.command == "mapping" and args.mapping_command == "validate":
        criteria = load_criteria(args.criteria)
        mappings = load_mappings(args.mappings)
        errors, warnings = validate_mappings(mappings, criteria)
        result = {"status": "error" if errors else "ok", "errors": errors, "warnings": warnings}
        _write_or_print(result)
        if errors:
            raise SystemExit(1)
    elif args.command == "criterion-claims" and args.claims_command == "backfill":
        store, criteria, mappings, out, dry_run, include_drafts, replace_source_claims, progress_enabled, progress_every = _backfill_inputs(args)
        result = backfill_criterion_claims(
            store=store,
            criteria=criteria,
            mappings=mappings,
            dry_run=dry_run,
            include_drafts=include_drafts,
            replace_source_claims=replace_source_claims,
            progress=_progress_reporter(progress_enabled),
            progress_every=progress_every,
        )
        _write_or_print(result, out)


if __name__ == "__main__":
    main()
