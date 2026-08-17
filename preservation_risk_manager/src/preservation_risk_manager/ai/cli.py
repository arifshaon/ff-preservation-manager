from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import (
    AIError,
    AIMessage,
    AIRequest,
    build_ai_provider,
    load_ai_config,
)


DEFAULT_SYSTEM_PROMPT = (
    "You are the File Format Preservation Risk Assistant. Use only evidence and tools "
    "supplied by the application when making preservation claims. If evidence is "
    "insufficient, say so explicitly."
)


def _load_schema(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    schema_path = Path(path).expanduser()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Response schema not found: {schema_path.resolve(strict=False)}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("Response schema must be a JSON object.")
    return schema


def show_info(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_config(args.config)
    return {
        "status": "ok",
        "configuration": config.redacted(),
        "note": "This command validates configuration shape only and does not contact the provider.",
    }


def run_query(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_config(args.config)
    provider = build_ai_provider(config)
    schema = _load_schema(args.response_schema)
    messages = (
        AIMessage("system", args.system or DEFAULT_SYSTEM_PROMPT),
        AIMessage("user", args.prompt),
    )
    request = AIRequest(
        messages=messages,
        response_schema=schema,
        response_schema_name=args.schema_name,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )
    return {
        "status": "ok",
        "provider": provider.describe(),
        "response": provider.generate(request).to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m preservation_risk_manager.ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="Validate and display redacted AI provider configuration.")
    info.add_argument("--config", required=True, help="Path to AI provider JSON configuration.")
    info.set_defaults(func=show_info)

    query = subparsers.add_parser("query", help="Send a manual test query through the configured AI provider.")
    query.add_argument("--config", required=True, help="Path to AI provider JSON configuration.")
    query.add_argument("--prompt", required=True, help="User prompt to send to the provider.")
    query.add_argument("--system", help="Optional system prompt override.")
    query.add_argument("--response-schema", help="Optional JSON Schema file for strict structured output.")
    query.add_argument("--schema-name", default="assistant_response", help="Structured-output schema name.")
    query.add_argument("--temperature", type=float, help="Override configured temperature.")
    query.add_argument("--max-output-tokens", type=int, help="Override configured output token limit.")
    query.set_defaults(func=run_query)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except (AIError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
