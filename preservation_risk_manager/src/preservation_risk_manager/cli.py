from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import (
    AIError,
    build_ai_provider,
    derive_answers_with_ai,
    load_ai_config,
)
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.policy_proposals import build_policy_change_proposal
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


def _compact_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Return provenance fields without long source bodies."""
    keys = (
        "claim_id",
        "source_claim_id",
        "_storage_key",
        "canonical_id",
        "criterion_id",
        "value",
        "answer_id",
        "source_id",
        "source_type",
        "source_record_id",
        "source_field",
        "mapping_rule_id",
        "mapping_version",
        "institution_id",
        "source_independence",
        "evidence_section",
        "review_status",
        "directness",
        "covers",
    )
    return {key: claim[key] for key in keys if key in claim and claim[key] is not None}


def _compact_answer_document(answer_document: dict[str, Any]) -> dict[str, Any]:
    compact = json.loads(json.dumps(answer_document, default=str))
    derivation = compact.get("derivation")
    if not isinstance(derivation, dict):
        return compact
    for result in derivation.values():
        if not isinstance(result, dict):
            continue
        claims = result.get("evidence_claims")
        if isinstance(claims, list):
            result["evidence_claims"] = [
                _compact_claim(claim)
                for claim in claims
                if isinstance(claim, dict)
            ]
    return compact


def _criterion_claims_summary(claims: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        key = (
            str(claim.get("criterion_id") or ""),
            str(claim.get("source_id") or ""),
            str(claim.get("value") or ""),
            str(claim.get("institution_id") or ""),
            str(claim.get("canonical_id") or ""),
        )
        group = grouped.setdefault(
            key,
            {
                "criterion_id": key[0],
                "source_id": key[1],
                "value": key[2],
                "institution_id": key[3] or None,
                "canonical_id": key[4],
                "count": 0,
                "source_record_ids": set(),
                "mapping_rule_ids": set(),
            },
        )
        group["count"] += 1
        if claim.get("source_record_id") is not None:
            group["source_record_ids"].add(str(claim["source_record_id"]))
        if claim.get("mapping_rule_id") is not None:
            group["mapping_rule_ids"].add(str(claim["mapping_rule_id"]))

    rows: list[dict[str, Any]] = []
    for group in grouped.values():
        row = dict(group)
        row["source_record_ids"] = sorted(row["source_record_ids"])
        row["mapping_rule_ids"] = sorted(row["mapping_rule_ids"])
        rows.append(row)
    rows.sort(key=lambda row: (
        row.get("criterion_id") or "",
        row.get("institution_id") or "",
        row.get("source_id") or "",
        row.get("canonical_id") or "",
        row.get("value") or "",
    ))

    return {
        "total_claims": len(claims),
        "groups": rows,
    }


def _resolved_analysis_context(args: argparse.Namespace) -> dict[str, Any]:
    framework_path = _require_file(args.framework, label="Framework file")
    framework = load_framework(framework_path)
    reader = _registry_reader_from_args(args)
    resolution = FormatResolver(reader).resolve(args.format)
    if not resolution.resolved or not resolution.format_doc:
        result = {"status": resolution.status, "resolution": _resolution_summary(resolution)}
        raise CliFailure(result, exit_code=2)

    criterion_claim_canonical_ids = reader.criterion_claim_canonical_ids(resolution.format_doc)
    criterion_claims = reader.get_criterion_claims_for_format(
        resolution.format_doc,
        institution_id=getattr(args, "institution", None),
    )
    evidence_pack = build_evidence_pack(
        resolution.format_doc,
        institution_id=getattr(args, "institution", None),
        criterion_claims=criterion_claims,
        include_unapproved=bool(getattr(args, "include_unapproved", False)),
    )
    answer_document = derive_answers(framework, evidence_pack)
    analysis = score_answers(framework, answer_document.get("scoring_answers") or answer_document["answers"])
    return {
        "framework": framework,
        "resolution": resolution,
        "criterion_claim_canonical_ids": criterion_claim_canonical_ids,
        "criterion_claims": criterion_claims,
        "evidence_pack": evidence_pack,
        "answer_document": answer_document,
        "analysis": analysis,
    }


def analyze_format(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    output_answer_document = (
        _compact_answer_document(context["answer_document"])
        if args.compact_evidence
        else context["answer_document"]
    )
    result: dict[str, Any] = {
        "status": "ok",
        "resolution": _resolution_summary(context["resolution"]),
        "format": context["evidence_pack"].get("format"),
        "scope": context["evidence_pack"].get("scope", "global"),
        "evidence_hash": evidence_hash(context["evidence_pack"]),
        "criterion_claim_canonical_ids": context["criterion_claim_canonical_ids"],
        "criterion_claims_used": len(context["criterion_claims"]),
        "derived_answers": output_answer_document,
        "analysis": context["analysis"],
    }
    if args.evidence_summary:
        result["criterion_claims_summary"] = _criterion_claims_summary(context["criterion_claims"])

    if args.institution:
        readiness_status, exposure_level = _posture_fields_from_args(args)
        result.update({
            "institution_id": args.institution,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                context["analysis"].get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })
    return result


def analyze_format_ai(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    ai_config = load_ai_config(_require_file(args.ai_config, label="AI config file"))
    provider = build_ai_provider(ai_config)
    ai_answer_document = derive_answers_with_ai(
        provider,
        context["framework"],
        context["evidence_pack"],
        context["answer_document"],
        max_evidence_items=args.max_ai_evidence_items,
    )
    ai_analysis = score_answers(
        context["framework"],
        ai_answer_document.get("scoring_answers") or ai_answer_document["answers"],
    )
    output_answer_document = (
        _compact_answer_document(ai_answer_document)
        if args.compact_evidence
        else ai_answer_document
    )
    result: dict[str, Any] = {
        "status": "ok",
        "mode": "ai_assisted",
        "provider": provider.describe(),
        "resolution": _resolution_summary(context["resolution"]),
        "format": context["evidence_pack"].get("format"),
        "scope": context["evidence_pack"].get("scope", "global"),
        "evidence_hash": evidence_hash(context["evidence_pack"]),
        "criterion_claim_canonical_ids": context["criterion_claim_canonical_ids"],
        "criterion_claims_used": len(context["criterion_claims"]),
        "derived_answers": output_answer_document,
        "deterministic_analysis": context["analysis"],
        "analysis": ai_analysis,
    }
    if args.evidence_summary:
        result["criterion_claims_summary"] = _criterion_claims_summary(context["criterion_claims"])

    if args.institution:
        readiness_status, exposure_level = _posture_fields_from_args(args)
        result.update({
            "institution_id": args.institution,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                ai_analysis.get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })
    return result


def propose_policy_change(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    evidence_pack = context["evidence_pack"]
    readiness_status, exposure_level = _posture_fields_from_args(args)
    local_risk_posture = None
    if args.institution:
        local_risk_posture = compute_local_risk_posture(
            context["analysis"].get("analysed_band"),
            readiness_status,
            exposure_level=exposure_level,
        )
    derived_answers = (
        _compact_answer_document(context["answer_document"])
        if args.compact_evidence
        else context["answer_document"]
    )
    return build_policy_change_proposal(
        goal=args.goal,
        resolution=_resolution_summary(context["resolution"]),
        format_doc=evidence_pack.get("format") or {},
        scope=evidence_pack.get("scope", "global"),
        evidence_hash=evidence_hash(evidence_pack),
        analysis=context["analysis"],
        criterion_claim_canonical_ids=context["criterion_claim_canonical_ids"],
        criterion_claims_summary=_criterion_claims_summary(context["criterion_claims"]),
        derived_answers=derived_answers,
        institution_id=args.institution,
        readiness_status=readiness_status,
        exposure_level=exposure_level,
        local_risk_posture=local_risk_posture,
    )


def _add_registry_source_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-json", help="Path to registry_builder registry.json export.")
    source.add_argument(
        "--storage-config",
        help="Path to a registry-builder storage block or full pipeline config containing 'storage'.",
    )


def _add_format_analysis_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    _add_registry_source_args(parser)
    parser.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    parser.add_argument("--institution", help="Optional institution ID for local posture analysis.")
    parser.add_argument("--readiness-status", default="Unknown", help="Institution readiness status when --institution is used.")
    parser.add_argument("--exposure-level", default="Unknown", help="Institution exposure level when --institution is used.")
    parser.add_argument("--include-unapproved", action="store_true", help="Include draft/rejected/superseded evidence claims.")
    parser.add_argument(
        "--evidence-summary",
        action="store_true",
        help="Add a compact criterion-claim summary grouped by criterion, source, value, institution, and canonical ID.",
    )
    parser.add_argument(
        "--compact-evidence",
        action="store_true",
        help="Suppress long evidence claim bodies in derived_answers while retaining provenance fields.",
    )


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
    _add_format_analysis_args(analyze_registry)
    analyze_registry.set_defaults(func=analyze_format)

    analyze_registry_ai = subparsers.add_parser(
        "analyze-format-ai",
        help=(
            "Run deterministic risk analysis, then use the configured AI provider only for unresolved "
            "or ambiguous framework questions before deterministic rescoring."
        ),
    )
    _add_format_analysis_args(analyze_registry_ai)
    analyze_registry_ai.add_argument(
        "--ai-config",
        required=True,
        help="Path to AI provider JSON configuration, for example config/ai.local.json.",
    )
    analyze_registry_ai.add_argument(
        "--max-ai-evidence-items",
        type=int,
        default=20,
        help="Maximum evidence items supplied to AI for each unresolved question.",
    )
    analyze_registry_ai.set_defaults(func=analyze_format_ai)

    propose = subparsers.add_parser(
        "propose-policy-change",
        help="Prepare an evidence-grounded draft policy/action recommendation package for human approval.",
    )
    propose.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    _add_registry_source_args(propose)
    propose.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    propose.add_argument("--institution", help="Optional institution ID for local policy proposal.")
    propose.add_argument("--readiness-status", default="Unknown", help="Institution readiness status when --institution is used.")
    propose.add_argument("--exposure-level", default="Unknown", help="Institution exposure level when --institution is used.")
    propose.add_argument("--include-unapproved", action="store_true", help="Include draft/rejected/superseded evidence claims.")
    propose.add_argument("--goal", required=True, help="Human goal for the draft policy/action recommendation.")
    propose.add_argument(
        "--compact-evidence",
        action="store_true",
        help="Suppress long evidence claim bodies in the LLM context while retaining provenance fields.",
    )
    propose.set_defaults(func=propose_policy_change)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except (AIError, FileNotFoundError) as exc:
        parser.exit(2, f"error: {exc}\n")
    except CliFailure as exc:
        print(json.dumps(exc.result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
