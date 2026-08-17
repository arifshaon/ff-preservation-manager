from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import build_ai_provider, load_ai_config
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.format_identification import AIFormatIdentificationPlugin, IdentificationResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.human_renderer import render_human_response
from preservation_risk_manager.request_api import RequestValidationError, execute_request


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
            help="AI provider config used only for optional format-identification fallback.",
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

    query = subparsers.add_parser(
        "query-json",
        help="Execute a structured preservation-risk request and return canonical JSON without AI routing.",
    )
    _add_common_args(query)
    request_source = query.add_mutually_exclusive_group(required=True)
    request_source.add_argument("--request", help="Path to structured request JSON.")
    request_source.add_argument("--request-json", help="Literal structured request JSON object.")
    _add_identification_args(query, machine_mode=True)
    return parser


def _identification_plugin(args: argparse.Namespace, *, existing_provider=None):
    if not bool(getattr(args, "enable_ai_identification", False)):
        return None

    provider = existing_provider
    if provider is None:
        config_path = getattr(args, "identification_ai_config", None)
        if not config_path:
            raise RequestValidationError(
                "--identification-ai-config is required with --enable-ai-identification in query-json mode."
            )
        config = load_ai_config(_require_file(config_path, label="Identification AI config file"))
        provider = build_ai_provider(config)

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
    response = execute_request(reader, framework, prepared_request)
    response["input"] = {
        "mode": "human_prompt",
        "prompt": args.question,
    }
    response["router"] = routed["router"]
    if identification is not None:
        response["identification"] = identification
    return response


def _query_json(args: argparse.Namespace) -> dict[str, Any]:
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    request = _load_request(args)
    plugin = _identification_plugin(args)
    prepared_request, identification = _resolve_request_format(reader, request, plugin=plugin)
    response = execute_request(reader, framework, prepared_request)
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
        # System integration is JSON-only. Human mode uses a concise readable
        # error unless the caller explicitly requested canonical JSON.
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
