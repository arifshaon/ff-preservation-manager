from __future__ import annotations

import argparse
import json
from pathlib import Path

from preservation_risk_manager.data_access import (
    JsonRegistryStore,
    RegistryAccessError,
    RegistryReader,
    load_storage_config,
)
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.registry_audit import (
    build_registry_risk_evidence_audit,
    write_registry_risk_evidence_audit,
)


def _require_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"{label} not found: {candidate.resolve(strict=False)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preservation_risk_manager audit-registry",
        description=(
            "Audit deterministic preservation-risk coverage across the whole registry, "
            "including question gaps, evidence sources, conflicts, band eligibility, "
            "LOC relationship scopes, and optional draft mapping uplift."
        ),
    )
    parser.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-json", help="Path to registry_builder registry.json export.")
    source.add_argument(
        "--storage-config",
        help="Path to registry-builder storage config or full pipeline config containing storage.",
    )
    parser.add_argument("--institution", help="Optional institution ID; default audit scope is global evidence only.")
    parser.add_argument(
        "--criteria",
        help="Optional registry-builder criteria vocabulary JSON. Use with --mappings-path for draft mapping uplift.",
    )
    parser.add_argument(
        "--mappings-path",
        help="Optional registry-builder criterion mapping directory/file. Use with --criteria for draft mapping uplift.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=25,
        help="Maximum conflict/gap samples and draft mapping opportunity rows to include (default: 25).",
    )
    parser.add_argument(
        "--out-dir",
        help="Optional output directory. Writes registry_risk_evidence_audit.json and .md.",
    )
    return parser


def _reader_from_args(args: argparse.Namespace) -> RegistryReader:
    if args.registry_json:
        registry_path = _require_file(args.registry_json, label="Registry JSON")
        return RegistryReader(store=JsonRegistryStore.from_registry_json(registry_path))
    storage_path = _require_file(args.storage_config, label="Storage config")
    return RegistryReader(storage_config=load_storage_config(storage_path))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.sample_limit < 1:
        parser.error("--sample-limit must be at least 1")
    if bool(args.criteria) != bool(args.mappings_path):
        parser.error("--criteria and --mappings-path must be supplied together")

    try:
        framework = load_framework(_require_file(args.framework, label="Framework"))
        reader = _reader_from_args(args)
        report = build_registry_risk_evidence_audit(
            reader,
            framework,
            institution_id=args.institution,
            criteria_path=args.criteria,
            mappings_path=args.mappings_path,
            sample_limit=args.sample_limit,
        )
        if args.out_dir:
            paths = write_registry_risk_evidence_audit(report, args.out_dir)
            result = {
                "status": "ok",
                "summary": report.get("summary"),
                "coverage_by_answered_questions": report.get("coverage_by_answered_questions"),
                "band_distribution": report.get("band_distribution"),
                "draft_mapping_opportunities": report.get("draft_mapping_opportunities"),
                "report_files": paths,
            }
        else:
            result = report
    except (FileNotFoundError, RegistryAccessError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0
