from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.batch_monitoring import run_batch_assessment
from preservation_risk_manager.integration_cli_human import _RateLimitCircuitProvider
from preservation_risk_manager.web_reports import parse_format_ids, write_report_artifacts


def _load_ids(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    for value in args.format_id or []:
        text = str(value or "").strip()
        if text:
            values.append(text)
    if args.input:
        path = Path(args.input).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Batch input file not found: {path.resolve(strict=False)}")
        values.extend(parse_format_ids(path.read_text(encoding="utf-8-sig"), filename=path.name))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    if not result:
        raise ValueError("Supply at least one --id value or --input TXT/CSV file.")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preservation_risk_manager batch-report",
        description="Generate a curator-oriented periodic preservation-risk report for selected format identifiers.",
    )
    parser.add_argument("--id", dest="format_id", action="append", help="Format identifier/PUID. Repeat for multiple formats.")
    parser.add_argument("--input", help="TXT/CSV watchlist. CSV may contain puid, pronom_puid, format_id, format or id.")
    parser.add_argument("--framework", required=True, help="Path to preservation-risk framework JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--storage-config", help="Registry-builder storage configuration.")
    source.add_argument("--registry-json", help="Registry JSON export.")
    parser.add_argument("--output", required=True, help="Directory for HTML/CSV/JSON/ZIP report artifacts.")
    parser.add_argument("--ai-mode", choices=("off", "synthesize", "fill-gaps"), default="off")
    parser.add_argument("--ai-config", help="AI provider configuration; required when --ai-mode is not off.")
    parser.add_argument("--institution", help="Institution ID. When supplied, the report uses institution scope.")
    parser.add_argument("--max-ai-evidence-items", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.ai_mode != "off" and not args.ai_config:
        raise SystemExit("--ai-config is required when --ai-mode is synthesize or fill-gaps")
    if int(args.max_ai_evidence_items) <= 0:
        raise SystemExit("--max-ai-evidence-items must be greater than zero")

    format_ids = _load_ids(args)
    reader = base._reader_from_args(args)
    framework = base.load_framework(base._require_file(args.framework, label="Framework file"))
    provider = None
    if args.ai_mode != "off":
        ai_config = base.load_ai_config(base._require_file(args.ai_config, label="AI config file"))
        provider = _RateLimitCircuitProvider(base.build_ai_provider(ai_config))

    def progress(value: int, message: str) -> None:
        print(f"[{value:3d}%] {message}")

    report = run_batch_assessment(
        reader=reader,
        framework=framework,
        format_ids=format_ids,
        scope="institution" if args.institution else "global",
        institution_id=args.institution,
        ai_mode=args.ai_mode,
        provider=provider,
        max_ai_evidence_items=int(args.max_ai_evidence_items),
        progress=progress,
    )
    downloads = write_report_artifacts(report, args.output)
    result = {
        "status": "ok",
        "report_type": report.get("report_type"),
        "generated_at": report.get("generated_at"),
        "input_count": report.get("input_count"),
        "successful_assessments": report.get("successful_assessments"),
        "failed_or_unresolved": report.get("failed_or_unresolved"),
        "governed_risk_counts": report.get("governed_risk_counts"),
        "ai_mode": report.get("ai_mode"),
        "ai_successful_syntheses": report.get("ai_successful_syntheses"),
        "artifacts": {name: str(Path(args.output) / filename) for name, filename in downloads.items()},
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0
