from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.posture import compute_local_risk_posture
from preservation_risk_manager.scoring import score_answers


class CliFailure(Exception):
    def __init__(self, result: dict[str, Any], *, exit_code: int = 2) -> None:
        super().__init__(result.get("status", "cli_failure"))
        self.result = result
        self.exit_code = exit_code


def _require_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    attempted = candidate.resolve(strict=False)
    raise FileNotFoundError(
        f"{label} not found: {attempted}. Pass an existing file path. "
        "If you need a registry export, run registry_builder first with exports enabled."
    )


def _load_json(path: str | Path) -> dict[str, Any]:
    path = _require_file(path, label="JSON input")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _answer_map(answer_document: dict[str, Any]) -> dict[str, Any]:
    answers = answer_document.get("answers")
    if isinstance(answers, dict):
        return answers
    return answer_document


def _posture_fields_from_args(args: argparse.Namespace) -> tuple[str, str]:
    readiness_status = str(getattr(args, "readiness_status", None) or "Unknown")
    exposure_level = str(getattr(args, "exposure_level", None) or "Unknown")
    return readiness_status, exposure_level


def _analysis_result(
    *,
    framework_path: str | Path,
    evidence_pack: dict[str, Any],
    answer_document: dict[str, Any],
    readiness_status: str = "Unknown",
    exposure_level: str = "Unknown",
) -> dict[str, Any]:
    framework = load_framework(_require_file(framework_path, label="Framework file"))
    analysis = score_answers(framework, _answer_map(answer_document))
    result: dict[str, Any] = {
        "status": "ok",
        "format": evidence_pack.get("format"),
        "scope": evidence_pack.get("scope", "global"),
        "evidence_hash": evidence_hash(evidence_pack),
        "analysis": analysis,
    }

    institution_id = evidence_pack.get("institution_id")
    if institution_id:
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


def analyze_fixture(args: argparse.Namespace) -> dict[str, Any]:
    evidence_pack = _load_json(args.evidence_pack)
    answer_document = _load_json(args.answers)
    readiness_status = str(answer_document.get("readiness_status") or "Unknown")
    exposure_level = str(answer_document.get("exposure_level") or "Unknown")
    return _analysis_result(
        framework_path=args.framework,
        evidence_pack=evidence_pack,
        answer_document=answer_document,
        readiness_status=readiness_status,
        exposure_level=exposure_level,
    )


def _resolution_message(resolution) -> str | None:
    if resolution.status == "ambiguous":
        noun = {
            "extension": "Extension",
            "mime_type": "MIME type",
            "authority_identifier": "Identifier",
            "verified_authority_identifier": "Verified identifier",
            "name": "Name",
            "alias": "Alias",
            "canonical_id": "Canonical ID",
        }.get(resolution.match_type or "", "Query")
        return (
            f"{noun} '{resolution.query}' matches {len(resolution.matches)} formats; "
            "specify a canonical ID or PUID."
        )
    if resolution.status == "not_found":
        return f"No format matched '{resolution.query}'."
    return None


def _resolution_summary(resolution) -> dict[str, Any]:
    summary = {
        "query": resolution.query,
        "status": resolution.status,
        "match_type": resolution.match_type,
        "match_count": len(resolution.matches),
        "matches": [
            {
                "canonical_id": match.get("canonical_id") or match.get("format_id") or match.get("id"),
                "preferred_name": match.get("preferred_name") or match.get("name") or match.get("label"),
            }
            for match in resolution.matches
        ],
    }
    message = _resolution_message(resolution)
    if message:
        summary["message"] = message
    return summary


def _registry_reader_from_args(args: argparse.Namespace) -> RegistryReader:
    registry_json = getattr(args, "registry_json", None)
    storage_config_path = getattr(args, "storage_config", None)
    if registry_json:
        registry_path = _require_file(registry_json, label="Registry JSON file")
        return RegistryReader(store=JsonRegistryStore.from_registry_json(registry_path))
    storage_path = _require_file(storage_config_path, label="Storage config file")
    return RegistryReader(storage_config=load_storage_config(storage_path))


def _canonical_id(format_doc: dict[str, Any]) -> str | None:
    value = format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id")
    return str(value) if value is not None else None


def analyze_format(args: argparse.Namespace) -> dict[str, Any]:
    framework_path = _require_file(args.framework, label="Framework file")
    framework = load_framework(framework_path)
    reader = _registry_reader_from_args(args)
    resolution = FormatResolver(reader).resolve(args.format)
    if not resolution.resolved or not resolution.format_doc:
        result = {"status": resolution.status, "resolution": _resolution_summary(resolution)}
        raise CliFailure(result, exit_code=2)

    canonical_id = _canonical_id(resolution.format_doc)
    criterion_claims = (
        reader.get_criterion_claims(canonical_id=canonical_id, institution_id=args.institution)
        if canonical_id
        else []
    )
    evidence_pack = build_evidence_pack(
        resolution.format_doc,
        institution_id=args.institution,
        criterion_claims=criterion_claims,
        include_unapproved=bool(args.include_unapproved),
    )
    answer_document = derive_answers(framework, evidence_pack)
    analysis = score_answers(framework, answer_document.get("scoring_answers") or answer_document["answers"])
    result: dict[str, Any] = {
        "status": "ok",
        "resolution": _resolution_summary(resolution),
        "format": evidence_pack.get("format"),
        "scope": evidence_pack.get("scope", "global"),
        "evidence_hash": evidence_hash(evidence_pack),
        "criterion_claims_used": len(criterion_claims),
        "derived_answers": answer_document,
        "analysis": analysis,
    }

    if args.institution:
        readiness_status, exposure_level = _posture_fields_from_args(args)
        result.update({
            "institution_id": args.institution,
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

    analyze_registry = subparsers.add_parser(
        "analyze-format",
        help="Resolve one format from a registry export or registry-builder store and run deterministic risk analysis.",
    )
    analyze_registry.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    source = analyze_registry.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-json", help="Path to registry_builder registry.json export.")
    source.add_argument(
        "--storage-config",
        help="Path to a registry-builder storage block or full pipeline config containing 'storage'.",
    )
    analyze_registry.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    analyze_registry.add_argument("--institution", help="Optional institution ID for local posture analysis.")
    analyze_registry.add_argument("--readiness-status", default="Unknown", help="Institution readiness status when --institution is used.")
    analyze_registry.add_argument("--exposure-level", default="Unknown", help="Institution exposure level when --institution is used.")
    analyze_registry.add_argument("--include-unapproved", action="store_true", help="Include draft/rejected/superseded evidence claims.")
    analyze_registry.set_defaults(func=analyze_format)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except FileNotFoundError as exc:
        parser.exit(2, f"error: {exc}\n")
    except CliFailure as exc:
        print(json.dumps(exc.result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
