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
from preservation_risk_manager.registry_audit import build_registry_risk_evidence_audit
from preservation_risk_manager.registry_audit_conflict_classification import (
    refine_conflict_semantics,
    render_conflict_semantics_markdown,
)
from preservation_risk_manager.registry_audit_diagnostics import (
    refine_registry_risk_evidence_diagnostics,
    render_registry_audit_diagnostics_markdown,
)
from preservation_risk_manager.registry_audit_governance import (
    refine_registry_risk_evidence_audit,
    write_refined_registry_risk_evidence_audit,
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
            "PUID production-path diagnostics, LOC relationship scopes, and optional draft mapping uplift."
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


def _compact_puid_diagnostics(report: dict) -> dict:
    puid = report.get("puid_diagnostics") or {}
    return {
        key: puid.get(key)
        for key in (
            "formats",
            "band_eligible_formats",
            "band_eligible_percent",
            "average_evidence_completeness",
            "coverage_by_answered_questions",
            "analysis_status_distribution",
            "band_distribution",
            "band_suppressed_reasons",
            "question_coverage",
            "gap_patterns",
            "source_support",
        )
    }


def _compact_conflict_diagnostics(report: dict) -> dict:
    conflicts = report.get("conflict_diagnostics") or {}
    return {
        key: conflicts.get(key)
        for key in (
            "total",
            "puid_format_conflicts",
            "non_puid_format_conflicts",
            "matches_base_audit_count",
            "by_question",
            "by_answer_combination",
            "by_source_combination",
            "by_question_and_source_combination",
        )
    }


def _compact_conflict_interpretation(report: dict) -> dict:
    data = report.get("conflict_interpretation") or {}
    return {
        key: data.get(key)
        for key in (
            "raw_derived_conflict_count",
            "genuine_evidence_conflicts",
            "composite_aggregations",
            "unclassified_conflicts",
            "puid_genuine_evidence_conflicts",
            "puid_composite_aggregations",
            "by_classification",
            "genuine_by_question",
            "genuine_by_evidence_field",
            "genuine_by_source_combination",
            "genuine_by_mapping_rule_combination",
            "composite_by_question",
            "composite_field_combinations",
            "note",
        )
    }


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
        report = refine_registry_risk_evidence_audit(
            report,
            reader,
            framework,
            institution_id=args.institution,
            criteria_path=args.criteria,
            mappings_path=args.mappings_path,
        )
        report = refine_registry_risk_evidence_diagnostics(
            report,
            reader,
            framework,
            institution_id=args.institution,
            sample_limit=args.sample_limit,
        )
        report = refine_conflict_semantics(
            report,
            reader,
            framework,
            institution_id=args.institution,
            sample_limit=args.sample_limit,
        )
        if args.out_dir:
            paths = write_refined_registry_risk_evidence_audit(report, args.out_dir)
            markdown_path = Path(paths["markdown"])
            diagnostic_markdown = render_registry_audit_diagnostics_markdown(report)
            conflict_markdown = render_conflict_semantics_markdown(report)
            with markdown_path.open("a", encoding="utf-8") as stream:
                stream.write("\n" + diagnostic_markdown)
                stream.write("\n" + conflict_markdown)
            result = {
                "status": "ok",
                "summary": report.get("summary"),
                "coverage_by_answered_questions": report.get("coverage_by_answered_questions"),
                "band_distribution": report.get("band_distribution"),
                "puid_diagnostics": _compact_puid_diagnostics(report),
                "conflict_diagnostics": _compact_conflict_diagnostics(report),
                "conflict_interpretation": _compact_conflict_interpretation(report),
                "draft_mapping_opportunities": report.get("draft_mapping_opportunities"),
                "report_files": paths,
            }
        else:
            result = report
    except (FileNotFoundError, RegistryAccessError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0
