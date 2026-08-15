from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.evidence_packs import evidence_hash
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.posture import compute_local_risk_posture
from preservation_risk_manager.scoring import score_answers


def _load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _answer_map(answer_document: dict[str, Any]) -> dict[str, Any]:
    answers = answer_document.get("answers")
    if isinstance(answers, dict):
        return answers
    return answer_document


def analyze_fixture(args: argparse.Namespace) -> dict[str, Any]:
    framework = load_framework(args.framework)
    evidence_pack = _load_json(args.evidence_pack)
    answer_document = _load_json(args.answers)

    analysis = score_answers(framework, _answer_map(answer_document))
    result: dict[str, Any] = {
        "format": evidence_pack.get("format"),
        "scope": evidence_pack.get("scope", "global"),
        "evidence_hash": evidence_hash(evidence_pack),
        "analysis": analysis,
    }

    institution_id = evidence_pack.get("institution_id")
    if institution_id:
        readiness_status = str(answer_document.get("readiness_status") or "Unknown")
        exposure_level = str(answer_document.get("exposure_level") or "Unknown")
        result.update({
            "institution_id": institution_id,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                analysis.get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="preservation_risk_manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze-fixture",
        help="Run framework scoring against fixture JSON files.",
    )
    analyze.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    analyze.add_argument("--evidence-pack", required=True, help="Path to evidence pack JSON.")
    analyze.add_argument("--answers", required=True, help="Path to controlled answer JSON.")
    analyze.set_defaults(func=analyze_fixture)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
