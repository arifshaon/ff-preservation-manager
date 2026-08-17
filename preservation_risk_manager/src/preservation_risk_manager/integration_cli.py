from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import build_ai_provider, load_ai_config
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.frameworks import load_framework
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
        help="Translate a human preservation-risk question into a controlled request and return canonical JSON.",
    )
    ask.add_argument("question", help="Natural-language preservation-risk question.")
    _add_common_args(ask)
    ask.add_argument("--ai-config", required=True, help="Path to AI provider configuration JSON.")
    ask.add_argument(
        "--institution",
        help="Default institution ID for the question, for example qnl. Explicit scope in the question may override it.",
    )
    ask.add_argument("--limit", type=int, default=100, help="Maximum number of formats for discovery/batch actions.")

    query = subparsers.add_parser(
        "query-json",
        help="Execute a structured preservation-risk request and return canonical JSON without AI routing.",
    )
    _add_common_args(query)
    request_source = query.add_mutually_exclusive_group(required=True)
    request_source.add_argument("--request", help="Path to structured request JSON.")
    request_source.add_argument("--request-json", help="Literal structured request JSON object.")
    return parser


def _ask(args: argparse.Namespace) -> dict[str, Any]:
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    config = load_ai_config(_require_file(args.ai_config, label="AI config file"))
    provider = build_ai_provider(config)
    default_scope = "institution" if args.institution else "global"
    routed = route_natural_language_request(
        provider,
        args.question,
        default_scope=default_scope,
        default_institution_id=args.institution,
        default_limit=args.limit,
    )
    response = execute_request(reader, framework, routed["request"])
    response["input"] = {
        "mode": "human_prompt",
        "prompt": args.question,
    }
    response["router"] = routed["router"]
    return response


def _query_json(args: argparse.Namespace) -> dict[str, Any]:
    reader = _reader_from_args(args)
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    request = _load_request(args)
    response = execute_request(reader, framework, request)
    response["input"] = {"mode": "structured_request"}
    return response


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = _ask(args) if args.command == "ask" else _query_json(args)
    except Exception as exc:  # Integration commands guarantee JSON output on errors.
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0
