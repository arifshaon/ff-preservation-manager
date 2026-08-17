from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest
from preservation_risk_manager.request_api import SUPPORTED_ACTIONS, normalize_request


REQUEST_ROUTER_SYSTEM_PROMPT = (
    "You are a request router for a file-format preservation risk system. "
    "Your only job is to convert the user's natural-language question into one supported "
    "structured action. Do not answer the preservation question, do not estimate risk, do not "
    "invent formats, and do not use general preservation knowledge. The application will execute "
    "the request against its registry and deterministic framework. Use assess_format for one format, "
    "search_formats for format discovery, assess_format_family for assessing all matching family "
    "members, and list_at_risk_formats when the user asks which formats are risky, concerning, at "
    "risk, Moderate, High, or should be worried about. If the user asks for at-risk formats without "
    "bands, use Moderate and High. If the user explicitly mentions QNL as the assessment scope, use "
    "scope institution with institution_id qnl; otherwise use global unless another institution ID "
    "is explicitly supplied."
)


def request_router_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(SUPPORTED_ACTIONS)},
            "format": {"type": ["string", "null"]},
            "query": {"type": ["string", "null"]},
            "filters": {
                "type": "object",
                "properties": {
                    "family": {"type": ["string", "null"]},
                    "risk_bands": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["Low", "Moderate", "High"]},
                    },
                },
                "required": ["family", "risk_bands"],
                "additionalProperties": False,
            },
            "scope": {"type": "string", "enum": ["global", "institution"]},
            "institution_id": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
        },
        "required": [
            "action",
            "format",
            "query",
            "filters",
            "scope",
            "institution_id",
            "limit",
        ],
        "additionalProperties": False,
    }


def route_natural_language_request(
    provider: AIProvider,
    prompt: str,
    *,
    default_scope: str = "global",
    default_institution_id: str | None = None,
    default_limit: int = 100,
) -> dict[str, Any]:
    """Translate a human question into a canonical request; never answer it directly."""
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("Natural-language request cannot be empty.")

    routing_context = {
        "user_question": text,
        "defaults": {
            "scope": default_scope,
            "institution_id": default_institution_id,
            "limit": default_limit,
        },
        "supported_actions": list(SUPPORTED_ACTIONS),
    }
    request = AIRequest(
        messages=(
            AIMessage("system", REQUEST_ROUTER_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Convert this user question into a structured request only.\n\n"
                + json.dumps(routing_context, indent=2, sort_keys=True),
            ),
        ),
        response_schema=request_router_schema(),
        response_schema_name="preservation_risk_request",
        temperature=0.0,
    )
    response = provider.generate(request)
    if not isinstance(response.structured, dict):
        raise AIProviderError("AI request router did not return a structured JSON object.")

    routed = dict(response.structured)
    # Apply caller defaults only when the model leaves the corresponding semantic
    # scope global/null. Explicit institution scope from the user's wording wins.
    if routed.get("scope") == "global" and default_scope == "institution" and default_institution_id:
        routed["scope"] = "institution"
        routed["institution_id"] = default_institution_id
    if not routed.get("limit"):
        routed["limit"] = default_limit

    normalized = normalize_request(routed)
    return {
        "request": normalized,
        "router": {
            "provider": response.provider,
            "model": response.model,
            "usage": response.to_dict()["usage"],
        },
    }
