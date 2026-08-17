from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.request_api import SUPPORTED_ACTIONS, normalize_request


REQUEST_ROUTER_SYSTEM_PROMPT = (
    "You are a request router for a file-format preservation risk system. "
    "Your only job is to convert the user's natural-language question into one supported "
    "structured action. Do not answer the preservation question, do not estimate risk, do not "
    "invent formats, and do not use general preservation knowledge. The application will execute "
    "the request against its registry and deterministic framework. Use assess_format for the overall "
    "assessment of one format. Use assess_format_questions when the user asks about one or more named "
    "assessment domains or specific preservation-risk questions for a format, such as software "
    "dependencies, governance, DRM, metadata, essential characteristics, or local feasibility. Use "
    "list_assessment_questions when the user asks what questions/domains the framework contains. Use "
    "search_formats only for format discovery, assess_format_family for assessing all matching family "
    "members, list_at_risk_formats when the user asks which formats are risky, concerning, at risk, "
    "Moderate, High, or should be worried about, list_evidence_gaps when the user asks why a format "
    "cannot be assessed, which formats need more evidence, what evidence is missing, or which formats "
    "are unassessed/partially assessed, and plan_evidence_remediation when the user asks what should be "
    "fixed, prioritized, mapped, enriched, or done next to improve assessment coverage. Use only domain "
    "and question IDs supplied in framework_question_catalog. For family-level list_at_risk_formats, "
    "list_evidence_gaps, or plan_evidence_remediation, put the family term in filters.family, not query. "
    "For a single-format question, put the format in format. If the user asks for at-risk formats without "
    "bands, use Moderate and High. If the user explicitly mentions QNL as the assessment scope, use scope "
    "institution with institution_id qnl; otherwise use global unless another institution ID is explicitly supplied."
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
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "question_ids": {"type": "array", "items": {"type": "string"}},
                    "content_type": {"type": ["string", "null"]},
                },
                "required": ["family", "risk_bands", "domains", "question_ids", "content_type"],
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
    """Repair mechanically inconsistent model routes without inferring risk."""
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
    for field in ("domains", "question_ids"):
        if not isinstance(filters.get(field), list):
            filters[field] = []
    if "content_type" not in filters:
        filters["content_type"] = None

    action = str(repaired.get("action") or "")
    query = str(repaired.get("query") or "").strip() or None
    format_value = str(repaired.get("format") or "").strip() or None

    if action == "search_formats" and family and risk_bands:
        repaired["action"] = "list_at_risk_formats"
        repaired["query"] = None
        repairs.append("search_formats_with_family_and_risk_bands->list_at_risk_formats")
        action = "list_at_risk_formats"

    if action == "search_formats" and not query and family:
        repaired["query"] = family
        repairs.append("search_formats.query<-filters.family")
        query = family
    elif action == "search_formats" and not query and format_value:
        repaired["query"] = format_value
        repairs.append("search_formats.query<-format")
        query = format_value

    if action in {"assess_format_family", "list_at_risk_formats"} and not family:
        inferred_family = query or format_value
        if inferred_family:
            filters["family"] = inferred_family
            repaired["query"] = None
            repaired["format"] = None
            repairs.append(f"{action}.filters.family<-query_or_format")
            family = inferred_family

    if action in {"list_evidence_gaps", "plan_evidence_remediation"} and not family and not format_value and query:
        repaired["format"] = query
        repaired["query"] = None
        repairs.append(f"{action}.format<-query")
        format_value = query

    has_question_selection = bool(filters.get("domains") or filters.get("question_ids") or filters.get("content_type"))
    if action == "assess_format" and has_question_selection:
        repaired["action"] = "assess_format_questions"
        repairs.append("assess_format_with_question_filters->assess_format_questions")
        action = "assess_format_questions"

    if action == "assess_format_questions" and not format_value and query:
        repaired["format"] = query
        repaired["query"] = None
        repairs.append("assess_format_questions.format<-query")

    return repaired, repairs


def _framework_catalog(framework: RiskFramework | None) -> dict[str, Any] | None:
    if framework is None:
        return None
    domains: dict[str, str | None] = {}
    questions: list[dict[str, Any]] = []
    for question in framework.questions:
        if question.domain_id:
            domains[question.domain_id] = question.domain_label
        questions.append({
            "question_id": question.id,
            "label": question.label,
            "domain_id": question.domain_id,
            "domain_label": question.domain_label,
            "aliases": list(question.aliases),
            "applicability": list(question.applicability),
        })
    return {
        "framework_id": framework.framework_id,
        "calibration_status": framework.calibration_status,
        "domains": [
            {"domain_id": domain_id, "label": domains[domain_id]}
            for domain_id in sorted(domains)
        ],
        "questions": questions,
    }


def route_natural_language_request(
    provider: AIProvider,
    prompt: str,
    *,
    framework: RiskFramework | None = None,
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
        "framework_question_catalog": _framework_catalog(framework),
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
