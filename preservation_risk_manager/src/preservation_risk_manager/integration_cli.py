from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from preservation_risk_manager.ai import (
    build_ai_provider,
    derive_answers_with_ai,
    load_ai_config,
    review_answers_with_ai,
    synthesize_with_ai,
    synthesize_with_web_research,
)
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_identification import (
    AIFormatIdentificationPlugin,
    IdentificationResolver,
    enrich_candidate_from_source_records,
)
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.human_renderer import render_human_response
from preservation_risk_manager.request_api import RequestValidationError, execute_request, normalize_request
from preservation_risk_manager.scoring import score_answers
from preservation_risk_manager.source_evidence import build_ai_source_evidence
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


def _require_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"{label} not found: {candidate.resolve(strict=False)}")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _validate_ai_options(args: argparse.Namespace) -> int:
    """Validate AI controls before registry reads or deterministic execution."""
    try:
        max_items = int(getattr(args, "max_ai_evidence_items", 20))
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("--max-ai-evidence-items must be an integer.") from exc
    if max_items <= 0:
        raise RequestValidationError("--max-ai-evidence-items must be greater than zero.")

    try:
        confidence = float(getattr(args, "identification_ai_min_confidence", 0.80))
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("--identification-ai-min-confidence must be numeric.") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise RequestValidationError("--identification-ai-min-confidence must be between 0 and 1.")
    return max_items


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
        choices=("off", "synthesize", "fill-gaps", "review-all"),
        default="off",
        help=(
            "Optional AI assistance after canonical format resolution. 'synthesize' produces the overall AI-assisted "
            "synthesis; when ai.web_research.enabled=true in the provider config it first verifies/supplements the "
            "registry evidence using cited public-web research. 'fill-gaps' also interprets unresolved framework "
            "questions; 'review-all' independently reviews framework evidence. Default: off."
        ),
    )
    parser.add_argument(
        "--max-ai-evidence-items",
        type=_positive_int,
        default=20,
        help="Maximum evidence items supplied to AI per framework question. Overall synthesis receives a bounded multiple of this value. Default: 20.",
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


def _candidate_extension_values(candidate: dict[str, Any]) -> set[str]:
    values = {str(value).strip().lower() for value in candidate.get("extensions") or [] if str(value).strip()}
    identifiers = candidate.get("identifiers") or {}
    if isinstance(identifiers, dict):
        values.update(str(value).strip().lower() for value in identifiers.get("extension") or [] if str(value).strip())
    return values


def _query_has_explicit_version(query: str, versions: set[str]) -> bool:
    lowered = str(query or "").lower()
    for version in versions:
        escaped = re.escape(version.lower())
        if re.search(rf"\b(?:version|ver|v|swf|flash)\s*[-:/]?\s*{escaped}\b", lowered):
            return True
    return False


def _promote_version_ambiguity(metadata: dict[str, Any]) -> dict[str, Any]:
    """Correct an AI no-match when its shortlist proves a version-family ambiguity."""
    if metadata.get("status") in {"resolved", "ambiguous"}:
        return metadata
    ai = metadata.get("ai") or {}
    if ai.get("status") not in {"no_match", "abstain"}:
        return metadata
    candidates = [item for item in ai.get("candidates") or [] if isinstance(item, dict)]
    if len(candidates) < 2:
        return metadata

    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        label = str(candidate.get("label") or "").strip().lower()
        version = str(candidate.get("version") or "").strip()
        canonical_id = str(candidate.get("canonical_id") or "").strip()
        if not label or not version or not canonical_id:
            continue
        grouped.setdefault(label, []).append(candidate)

    query = str(metadata.get("input") or "").strip().lower()
    query_tokens = set(re.findall(r"[a-z0-9]+", query))
    eligible: list[tuple[int, str, list[dict[str, Any]]]] = []
    for label, group in grouped.items():
        versions = {str(item.get("version") or "").strip() for item in group if str(item.get("version") or "").strip()}
        if len(group) < 2 or len(versions) < 2 or _query_has_explicit_version(query, versions):
            continue
        label_tokens = {token for token in re.findall(r"[a-z0-9]+", label) if len(token) >= 3}
        shared_extensions: set[str] | None = None
        for item in group:
            item_extensions = _candidate_extension_values(item)
            shared_extensions = item_extensions if shared_extensions is None else shared_extensions.intersection(item_extensions)
        family_signal = bool(label_tokens.intersection(query_tokens)) or bool((shared_extensions or set()).intersection(query_tokens))
        if family_signal:
            eligible.append((len(group), label, group))

    if not eligible:
        return metadata
    eligible.sort(key=lambda item: (-item[0], item[1]))
    _, label, group = eligible[0]
    candidate_ids = [str(item.get("canonical_id")) for item in group]
    promoted = dict(metadata)
    promoted.update({
        "status": "ambiguous",
        "match_type": "programmatic_version_ambiguity",
        "method": "ai_fallback_no_match_programmatic_ambiguity",
        "ambiguity_candidate_canonical_ids": candidate_ids,
        "programmatic_ambiguity": {
            "reason": "family_matched_but_version_not_supplied",
            "family_label": label,
            "candidate_count": len(candidate_ids),
            "candidate_canonical_ids": candidate_ids,
            "ai_status_retained_for_audit": ai.get("status"),
        },
    })
    return promoted


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
            if row.get("version") is not None:
                metadata["resolved_version"] = str(row.get("version"))
    else:
        metadata = _promote_version_ambiguity(metadata)
    return prepared, metadata


def _identification_ambiguity_response(framework, request: dict[str, Any], identification: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep a real identification ambiguity from being overwritten as not_found."""
    if not identification or identification.get("status") != "ambiguous":
        return None
    normalized_request = normalize_request(request)
    ai = identification.get("ai") or {}
    wanted_values = identification.get("ambiguity_candidate_canonical_ids") or ai.get("candidate_canonical_ids") or []
    wanted = {str(value) for value in wanted_values if str(value).strip()}
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


def _ai_format_context(reader: RegistryReader, format_doc: dict[str, Any]) -> dict[str, Any]:
    """Recover source-declared version/signature identity for AI interpretation."""
    try:
        return enrich_candidate_from_source_records(reader, format_doc)
    except Exception:
        return format_doc


def _web_research_enabled(provider: Any) -> bool:
    config = getattr(provider, "config", None)
    return bool(getattr(config, "web_research_enabled", False))


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
    """Attach policy-guided AI synthesis and optional question-level AI analysis."""
    if ai_mode == "off" or response.get("status") != "ok":
        return response
    if str(request.get("action") or "").strip() != "assess_format":
        response["ai_risk_assessment"] = {
            "status": "not_applicable",
            "ai_mode": ai_mode,
            "reason": "ai_risk_assessment_currently_requires_assess_format",
        }
        return response

    max_items = int(max_evidence_items)
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
    format_doc = _ai_format_context(reader, resolution.format_doc)
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(format_doc, institution_id=institution_id, criterion_claims=claims)
    if format_doc.get("version") is not None:
        pack["format"]["version"] = str(format_doc.get("version"))
    if format_doc.get("versions"):
        pack["format"]["versions"] = [str(value) for value in format_doc.get("versions")]
    if format_doc.get("internal_signature_names"):
        pack["format"]["internal_signature_names"] = [str(value) for value in format_doc.get("internal_signature_names")]

    deterministic_answers = derive_answers(framework, pack)
    deterministic_analysis = score_answers(
        framework,
        deterministic_answers.get("scoring_answers") or deterministic_answers["answers"],
    )

    source_evidence = build_ai_source_evidence(
        reader,
        format_doc,
        max_source_records=max(40, max_items * 3),
        max_items=max(60, max_items * 5),
    )
    pack["ai_source_evidence"] = source_evidence

    result_payload = response.get("result") if isinstance(response.get("result"), dict) else {}
    external_context = result_payload.get("external_risk_context") if isinstance(result_payload, dict) else {}
    if not isinstance(external_context, dict):
        external_context = {}

    policy = load_synthesis_policy()
    governed_synthesis = (
        external_context.get("policy_synthesized_risk")
        or external_context.get("registry_synthesized_risk")
        or {"assessed": False, "semantic_level": None, "semantic_label": None}
    )
    web_research = _web_research_enabled(provider)
    try:
        synthesis_args = {
            "provider": provider,
            "format_context": pack.get("format") or {},
            "policy": policy,
            "risk_assessments": [
                dict(item) for item in external_context.get("assessments") or [] if isinstance(item, dict)
            ],
            "criterion_claims": [dict(item) for item in claims if isinstance(item, dict)],
            "source_evidence": [dict(item) for item in source_evidence if isinstance(item, dict)],
            "max_evidence_items": max(40, max_items * 4),
        }
        if web_research:
            ai_synthesis = synthesize_with_web_research(
                governed_synthesis=governed_synthesis,
                framework=framework,
                **synthesis_args,
            )
        else:
            ai_synthesis = synthesize_with_ai(**synthesis_args)
        response["ai_synthesis"] = ai_synthesis
        if isinstance(result_payload, dict):
            result_payload["overall_synthesized_risk"] = ai_synthesis.get("overall_synthesized_risk")
    except Exception as exc:
        response["ai_synthesis"] = {
            "status": "error_config_synthesis_retained",
            "ai_mode": ai_mode,
            "web_research_enabled": web_research,
            "provider": provider.describe(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "overall_synthesized_risk": governed_synthesis,
            "authority_boundary": (
                "AI research/synthesis failed; the config-driven deterministic synthesis was retained unchanged."
            ),
        }
        if isinstance(result_payload, dict):
            result_payload["overall_synthesized_risk"] = governed_synthesis

    if ai_mode == "synthesize":
        response["ai_risk_assessment"] = {
            "status": "synthesis_only",
            "ai_mode": ai_mode,
            "web_research_enabled": web_research,
            "question_level_ai_requested": False,
        }
        return response

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
        source_record_keys = {
            (str(item.get("source_id") or ""), str(item.get("source_record_id") or ""))
            for item in source_evidence
            if item.get("source_id") or item.get("source_record_id")
        }
        response["ai_risk_assessment"] = {
            "status": "ok",
            "ai_mode": ai_mode,
            "provider": provider.describe(),
            "web_research_enabled_for_overall_synthesis": web_research,
            "evidence_hash": evidence_hash(pack),
            "criterion_claims_used": len(claims),
            "ai_source_evidence_items": len(source_evidence),
            "ai_source_records_used": len(source_record_keys),
            "ai_format_context": pack.get("format") or {},
            "deterministic_analysis": deterministic_analysis,
            "analysis": ai_analysis,
            "derived_answers": ai_answers,
            "authority_boundary": (
                "Question-level deterministic answers and scores use approved criterion evidence only. AI may "
                "additionally interpret bounded source-native evidence for unresolved questions; it cannot replace "
                "deterministically resolved answers, change framework governance, or create policy. Overall source "
                "risk synthesis is handled separately through the versioned synthesis policy and, when explicitly "
                "enabled in provider config, registry-first cited web research."
            ),
        }
    except Exception as exc:
        response["ai_risk_assessment"] = {
            "status": "error_deterministic_retained",
            "ai_mode": ai_mode,
            "provider": provider.describe(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "ai_source_evidence_items": len(source_evidence),
            "deterministic_analysis": deterministic_analysis,
        }
    return response


def _ask(args: argparse.Namespace) -> dict[str, Any]:
    max_items = _validate_ai_options(args)
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
    routed_request = normalize_request(routed["request"])
    plugin = _identification_plugin(args, existing_provider=provider)
    prepared_request, identification = _resolve_request_format(reader, routed_request, plugin=plugin)
    response = _identification_ambiguity_response(framework, routed_request, identification)
    if response is None:
        response = execute_request(reader, framework, prepared_request)
        response = _apply_ai_risk_assessment(
            reader,
            framework,
            prepared_request,
            response,
            provider=provider,
            ai_mode=args.ai_mode,
            max_evidence_items=max_items,
        )
    response["input"] = {"mode": "human_prompt", "prompt": args.question}
    response["router"] = routed["router"]
    if identification is not None:
        response["identification"] = identification
    return response


def _query_json(args: argparse.Namespace) -> dict[str, Any]:
    max_items = _validate_ai_options(args)
    request = normalize_request(_load_request(args))
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
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
                max_evidence_items=max_items,
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
