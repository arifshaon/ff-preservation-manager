from __future__ import annotations

from copy import deepcopy
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
    "search_formats only for format discovery, assess_format_family for assessing all matching family "
    "members, and list_at_risk_formats when the user asks which formats are risky, concerning, at "
    "risk, Moderate, High, or should be worried about. For list_at_risk_formats, put the family term "
    "in filters.family, not query. If the user asks for at-risk formats without bands, use Moderate "
    "and High. If the user explicitly mentions QNL as the assessment scope, use scope institution "
    "with institution_id qnl; otherwise use global unless another institution ID is explicitly supplied."
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


def _repair_routed_request(routed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Repair mechanically inconsistent model routes without inferring risk.

    The AI remains responsible for intent routing, but the application enforces
    a valid canonical request shape. Repairs use only fields already returned by
    the router; they do not inspect registry evidence or answer the preservation
    question.
    """
    repaired = deepcopy(routed)
    repairs: list[str] = []
    filters = repaired.get("filters")
    if not isinstance(filters, dict):
        filters = {}
        repaired["filters"] = filters
    family = str(filters.get("family") or "").strip() or None
    risk_bands = filters.get("risk_bands")
    if not isinstance(risk_bands, list):
        risk_bands = []
        filters["risk_bands"] = risk_bands

    action = str(repaired.get("action") or "")
    query = str(repaired.get("query") or "").strip() or None
    format_value = str(repaired.get("format") or "").strip() or None

    # Common router slip: it recognizes a family and risk bands but labels the
    # action as discovery. Preserve the structured family/bands and use the
    # canonical at-risk action.
    if action == "search_formats" and family and risk_bands:
        repaired["action"] = "list_at_risk_formats"
        repaired["query"] = None
        repairs.append("search_formats_with_family_and_risk_bands->list_at_risk_formats")
        action = "list_at_risk_formats"

    # A discovery request with a family but no query can be repaired directly.
    if action == "search_formats" and not query and family:
        repaired["query"] = family
        repairs.append("search_formats.query<-filters.family")
        query = family
    elif action == "search_formats" and not query and format_value:
        repaired["query"] = format_value
        repairs.append("search_formats.query<-format")
        query = format_value

    # Family actions sometimes receive the subject in query/format rather than
    # filters.family. Move it into the canonical location.
    if action in {"assess_format_family", "list_at_risk_formats"} and not family:
        inferred_family = query or format_value
        if inferred_family:
            filters["family"] = inferred_family
            repaired["query"] = None
            repaired["format"] = None
            repairs.append(f"{action}.filters.family<-query_or_format")
            family = inferred_family

    return repaired, repairs


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

    raw_routed = dict(response.structured)
    routed, repairs = _repair_routed_request(raw_routed)

    # Apply caller defaults only when the model leaves the corresponding semantic
    # scope global/null. Explicit institution scope from the user's wording wins.
    if routed.get("scope") == "global" and default_scope == "institution" and default_institution_id:
        routed["scope"] = "institution"
        routed["institution_id"] = default_institution_id
        repairs.append("default_institution_scope_applied")
    if not routed.get("limit"):
        routed["limit"] = default_limit
        repairs.append("default_limit_applied")

    normalized = normalize_request(routed)
    return {
        "request": normalized,
        "router": {
            "provider": response.provider,
            "model": response.model,
            "usage": response.to_dict()["usage"],
            "repairs": repairs,
            "raw_request": raw_routed,
        },
    }
