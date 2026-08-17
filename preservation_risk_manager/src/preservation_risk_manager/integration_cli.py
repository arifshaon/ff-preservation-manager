from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import (
    build_ai_provider,
    derive_answers_with_ai,
    load_ai_config,
    review_answers_with_ai,
)
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_identification import AIFormatIdentificationPlugin, IdentificationResolver
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.human_renderer import render_human_response
from preservation_risk_manager.request_api import RequestValidationError, execute_request, normalize_request
from preservation_risk_manager.scoring import score_answers


def _require_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"{label} not found: {candidate.resolve(strict=False)}")


def _reader_from_args(args: argparse.Namespace) -> RegistryReader:
    if getattr(args, "registry_json", None):
        path = _require_file(args.registry_json, label="Registry JSON file")
        return RegistryReader(store=JsonRegistryStore.from_registry_json(path))
    path = _require_file(args.storage_config, label="Storage config file")
    return RegistryReader(storage_config=load_storage_config(path))


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-json", help="Path to registry JSON export.")
    source.add_argument("--storage-config", help="Path to registry-builder storage config.")


def _add_identification_args(parser: argparse.ArgumentParser, *, machine_mode: bool) -> None:
    parser.add_argument(
        "--enable-ai-identification",
        action="store_true",
        help=(
            "Enable bounded AI fallback when deterministic format identification is unresolved or ambiguous. "
            "AI may select only from local canonical registry candidates."
        ),
    )
    parser.add_argument(
        "--identification-ai-min-confidence",
        type=float,
        default=0.80,
        help="Minimum AI confidence required to accept a local candidate. Default: 0.80.",
    )
    if machine_mode:
        parser.add_argument(
            "--identification-ai-config",
            help=(
                "AI provider config for optional format-identification fallback. For backward compatibility this "
                "may also supply the provider for --ai-mode when --ai-config is omitted."
            ),
        )


def _add_ai_risk_args(parser: argparse.ArgumentParser, *, machine_mode: bool) -> None:
    parser.add_argument(
        "--ai-mode",
        choices=("off", "fill-gaps", "review-all"),
        default="off",
        help=(
            "Optional AI-assisted risk assessment after canonical format resolution. 'fill-gaps' interprets only "
            "unresolved/ambiguous evidence; 'review-all' independently reviews raw evidence without replacing "
            "deterministic scoring inputs. Default: off."
        ),
    )
    parser.add_argument(
        "--max-ai-evidence-items",
        type=int,
        default=20,
        help="Maximum evidence items supplied to AI per framework question. Default: 20.",
    )
    if machine_mode:
        parser.add_argument(
            "--ai-config",
            help=(
                "AI provider config for --ai-mode and, when enabled, format identification. If omitted, "
                "--identification-ai-config is accepted for backward compatibility."
            ),
        )


def _load_request(args: argparse.Namespace) -> dict[str, Any]:
    if args.request:
        path = _require_file(args.request, label="Request JSON file")
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(args.request_json)
    if not isinstance(data, dict):
        raise RequestValidationError("Structured request must be a JSON object.")
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="preservation_risk_manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask = subparsers.add_parser(
        "ask",
        help="Answer a human preservation-risk question using controlled routing and deterministic evidence.",
    )
    ask.add_argument("question", help="Natural-language preservation-risk question.")
    _add_common_args(ask)
    ask.add_argument("--ai-config", required=True, help="Path to AI provider configuration JSON.")
    ask.add_argument(
        "--institution",
        help="Default institution ID for the question, for example qnl. Explicit scope in the question may override it.",
    )
    ask.add_argument("--limit", type=int, default=100, help="Maximum number of formats for discovery/batch actions.")
    ask.add_argument(
        "--json",
        action="store_true",
        help="Return the canonical JSON response instead of the default detailed human-readable answer.",
    )
    _add_identification_args(ask, machine_mode=False)
    _add_ai_risk_args(ask, machine_mode=False)

    query = subparsers.add_parser(
        "query-json",
        help="Execute a structured preservation-risk request and return canonical JSON without AI routing.",
    )
    _add_common_args(query)
    request_source = query.add_mutually_exclusive_group(required=True)
    request_source.add_argument("--request", help="Path to structured request JSON.")
    request_source.add_argument("--request-json", help="Literal structured request JSON object.")
    _add_identification_args(query, machine_mode=True)
    _add_ai_risk_args(query, machine_mode=True)
    return parser


def _provider_for_enabled_ai(args: argparse.Namespace, *, existing_provider=None):
    needs_provider = bool(getattr(args, "enable_ai_identification", False)) or str(
        getattr(args, "ai_mode", "off") or "off"
    ) != "off"
    if not needs_provider:
        return existing_provider
    if existing_provider is not None:
        return existing_provider

    config_path = getattr(args, "ai_config", None) or getattr(args, "identification_ai_config", None)
    if not config_path:
        raise RequestValidationError(
            "AI is enabled but no provider config was supplied. Pass --ai-config (preferred) or "
            "--identification-ai-config."
        )
    config = load_ai_config(_require_file(config_path, label="AI config file"))
    return build_ai_provider(config)


def _identification_plugin(args: argparse.Namespace, *, existing_provider=None):
    if not bool(getattr(args, "enable_ai_identification", False)):
        return None

    provider = _provider_for_enabled_ai(args, existing_provider=existing_provider)
    confidence = float(getattr(args, "identification_ai_min_confidence", 0.80))
    if confidence < 0.0 or confidence > 1.0:
        raise RequestValidationError("--identification-ai-min-confidence must be between 0 and 1.")
    return AIFormatIdentificationPlugin(provider, minimum_confidence=confidence)


def _resolve_request_format(
    reader: RegistryReader,
    request: dict[str, Any],
    *,
    plugin=None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    prepared = dict(request)
    raw_format = prepared.get("format")
    if raw_format is None or not str(raw_format).strip():
        return prepared, None

    identification = IdentificationResolver(reader, plugin=plugin).resolve(str(raw_format))
    metadata = identification.to_dict()
    if identification.resolved and identification.resolution.format_doc:
        row = identification.resolution.format_doc
        canonical_id = row.get("canonical_id") or row.get("format_id") or row.get("id")
        if canonical_id:
            prepared["format"] = str(canonical_id)
            metadata["resolved_canonical_id"] = str(canonical_id)
            metadata["resolved_label"] = (
                row.get("preferred_name") or row.get("format_name") or row.get("name") or row.get("label")
            )
    return prepared, metadata


def _identification_ambiguity_response(framework, request: dict[str, Any], identification: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep a real identification ambiguity from being overwritten as not_found."""
    if not identification or identification.get("status") != "ambiguous":
        return None
    normalized_request = normalize_request(request)
    ai = identification.get("ai") or {}
    wanted = {str(value) for value in ai.get("candidate_canonical_ids") or [] if str(value).strip()}
    candidates = [
        candidate
        for candidate in ai.get("candidates") or []
        if isinstance(candidate, dict) and (not wanted or str(candidate.get("canonical_id") or "") in wanted)
    ]
    return {
        "status": "ambiguous",
        "request": normalized_request,
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "calibration_status": framework.calibration_status,
            "banding_enabled": framework.banding_enabled,
        },
        "scope": normalized_request["scope"],
        "institution_id": normalized_request.get("institution_id"),
        "resolution": {
            "query": identification.get("input"),
            "status": "ambiguous",
            "match_type": identification.get("match_type") or "ai_candidate_ambiguity",
            "matches": candidates,
        },
        "risk_assessment": {
            "status": "not_run",
            "reason": "canonical_format_not_uniquely_resolved",
        },
    }


def _apply_ai_risk_assessment(
    reader: RegistryReader,
    framework,
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    provider,
    ai_mode: str,
    max_evidence_items: int,
) -> dict[str, Any]:
    """Attach AI-assisted risk analysis after a canonical single-format assessment.

    This deliberately sits outside ``request_api.execute_request`` so the canonical
    request executor remains deterministic. The deterministic result is retained in
    the normal response; AI output is an additive audit/interpretation layer.
    """
    if ai_mode == "off" or response.get("status") != "ok":
        return response
    if str(request.get("action") or "") != "assess_format":
        response["ai_risk_assessment"] = {
            "status": "not_applicable",
            "ai_mode": ai_mode,
            "reason": "ai_risk_assessment_currently_requires_assess_format",
        }
        return response

    try:
        max_items = int(max_evidence_items)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("--max-ai-evidence-items must be an integer.") from exc
    if max_items <= 0:
        raise RequestValidationError("--max-ai-evidence-items must be greater than zero.")

    format_token = str(request.get("format") or "").strip()
    resolution = FormatResolver(reader).resolve(format_token)
    if not resolution.resolved or not resolution.format_doc:
        response["ai_risk_assessment"] = {
            "status": "not_run",
            "ai_mode": ai_mode,
            "reason": "canonical_format_not_resolved",
        }
        return response

    institution_id = response.get("institution_id") if response.get("scope") == "institution" else None
    claims = reader.get_criterion_claims_for_format(resolution.format_doc, institution_id=institution_id)
    pack = build_evidence_pack(resolution.format_doc, institution_id=institution_id, criterion_claims=claims)
    deterministic_answers = derive_answers(framework, pack)
    deterministic_analysis = score_answers(
        framework,
        deterministic_answers.get("scoring_answers") or deterministic_answers["answers"],
    )

    try:
        if ai_mode == "review-all":
            ai_answers = review_answers_with_ai(
                provider,
                framework,
                pack,
                deterministic_answers,
                max_evidence_items=max_items,
            )
        else:
            ai_answers = derive_answers_with_ai(
                provider,
                framework,
                pack,
                deterministic_answers,
                max_evidence_items=max_items,
            )
        ai_analysis = score_answers(framework, ai_answers.get("scoring_answers") or ai_answers["answers"])
        response["ai_risk_assessment"] = {
            "status": "ok",
            "ai_mode": ai_mode,
            "provider": provider.describe(),
            "evidence_hash": evidence_hash(pack),
            "criterion_claims_used": len(claims),
            "deterministic_analysis": deterministic_analysis,
            "analysis": ai_analysis,
            "derived_answers": ai_answers,
            "authority_boundary": (
                "AI may interpret supplied evidence according to the selected mode; deterministic evidence, "
                "framework rules, score/band governance, and policy remain authoritative."
            ),
        }
    except Exception as exc:
        response["ai_risk_assessment"] = {
            "status": "error_deterministic_retained",
            "ai_mode": ai_mode,
            "provider": provider.describe(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "deterministic_analysis": deterministic_analysis,
        }
    return response


def _ask(args: argparse.Namespace) -> dict[str, Any]:
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    config = load_ai_config(_require_file(args.ai_config, label="AI config file"))
    provider = build_ai_provider(config)
    default_scope = "institution" if args.institution else "global"
    routed = route_natural_language_request(
        provider,
        args.question,
        framework=framework,
        default_scope=default_scope,
        default_institution_id=args.institution,
        default_limit=args.limit,
    )
    plugin = _identification_plugin(args, existing_provider=provider)
    prepared_request, identification = _resolve_request_format(reader, routed["request"], plugin=plugin)
    response = _identification_ambiguity_response(framework, routed["request"], identification)
    if response is None:
        response = execute_request(reader, framework, prepared_request)
        response = _apply_ai_risk_assessment(
            reader,
            framework,
            prepared_request,
            response,
            provider=provider,
            ai_mode=args.ai_mode,
            max_evidence_items=args.max_ai_evidence_items,
        )
    response["input"] = {"mode": "human_prompt", "prompt": args.question}
    response["router"] = routed["router"]
    if identification is not None:
        response["identification"] = identification
    return response


def _query_json(args: argparse.Namespace) -> dict[str, Any]:
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    request = _load_request(args)
    provider = _provider_for_enabled_ai(args)
    plugin = _identification_plugin(args, existing_provider=provider)
    prepared_request, identification = _resolve_request_format(reader, request, plugin=plugin)
    response = _identification_ambiguity_response(framework, request, identification)
    if response is None:
        response = execute_request(reader, framework, prepared_request)
        if args.ai_mode != "off":
            response = _apply_ai_risk_assessment(
                reader,
                framework,
                prepared_request,
                response,
                provider=provider,
                ai_mode=args.ai_mode,
                max_evidence_items=args.max_ai_evidence_items,
            )
    response["input"] = {"mode": "structured_request"}
    if identification is not None:
        response["identification"] = identification
    return response


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = _ask(args) if args.command == "ask" else _query_json(args)
    except Exception as exc:
        error = {"status": "error", "error": str(exc)}
        if args.command == "query-json" or getattr(args, "json", False):
            print(json.dumps(error, indent=2, sort_keys=True))
        else:
            print(f"The request could not be completed: {exc}")
        return 2

    if args.command == "ask" and not args.json:
        print(render_human_response(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0