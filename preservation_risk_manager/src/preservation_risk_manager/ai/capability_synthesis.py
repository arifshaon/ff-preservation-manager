from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT = (
    "You are assisting with a digital-preservation risk assessment. The application supplies the resolved format, "
    "collected registry/source evidence, the deterministic/config synthesis, the QNL synthesis policy, and the "
    "assessment framework. Treat all supplied evidence and methodology as important context. Produce an AI-assisted "
    "synthesized preservation risk using the capabilities available to you. You may use external information when "
    "useful and available, but do not misattribute it to NARA, DPC, LOC, PRONOM, or another supplied source. Preserve "
    "source-native statements as source statements. Missing evidence is not Low risk. Explain material agreement or "
    "disagreement with the governed baseline, and report confidence and uncertainty."
)


def _safe(value: Any, *, max_string: int = 5000) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "…"
    if isinstance(value, dict):
        return {str(key): _safe(item, max_string=max_string) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, max_string=max_string) for item in list(value)[:150]]
    return _safe(str(value), max_string=max_string)


def _framework_summary(framework: Any | None) -> dict[str, Any] | None:
    if framework is None:
        return None
    return {
        "framework_id": getattr(framework, "framework_id", None),
        "version": getattr(framework, "version", None),
        "calibration_status": getattr(framework, "calibration_status", None),
        "questions": [
            {
                "question_id": getattr(question, "id", None),
                "label": getattr(question, "label", None),
                "domain_id": getattr(question, "domain_id", None),
                "domain_label": getattr(question, "domain_label", None),
                "critical": bool(getattr(question, "critical", False)),
                "evidence_fields": list(getattr(question, "evidence_fields", ()) or ()),
                "applicability": list(getattr(question, "applicability", ()) or ()),
            }
            for question in getattr(framework, "questions", ())
        ],
    }


def _response_schema(policy: SynthesisPolicy) -> dict[str, Any]:
    levels = list(policy.level_by_id)
    consideration = {
        "type": "object",
        "properties": {
            "finding": {"type": "string"},
            "basis": {
                "type": "string",
                "enum": ["registry_evidence", "external_information", "model_reasoning", "mixed"],
            },
            "risk_effect": {
                "type": "string",
                "enum": ["raises_concern", "reduces_concern", "neutral", "uncertain"],
            },
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["finding", "basis", "risk_effect", "database_evidence_refs"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "semantic_level": {"type": "string", "enum": levels + ["unassessed"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "considerations": {"type": "array", "items": consideration},
            "config_rules_considered": {"type": "array", "items": {"type": "string"}},
            "governed_baseline_relation": {
                "type": "string",
                "enum": ["same", "higher_concern", "lower_concern", "not_comparable"],
            },
            "uncertainty": {"type": "string"},
        },
        "required": [
            "semantic_level", "confidence", "rationale", "database_evidence_refs",
            "considerations", "config_rules_considered", "governed_baseline_relation", "uncertainty",
        ],
        "additionalProperties": False,
    }


def _validate_with_warnings(
    response: AIResponse,
    *,
    database_evidence: list[dict[str, Any]],
    policy: SynthesisPolicy,
) -> dict[str, Any]:
    data = response.structured
    if not isinstance(data, dict):
        raise AIProviderError("AI synthesis did not return a structured JSON object.")

    allowed_levels = set(policy.level_by_id) | {"unassessed"}
    level = str(data.get("semantic_level") or "")
    if level not in allowed_levels:
        raise AIProviderError(f"AI synthesis returned unsupported level '{level}'.")
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIProviderError("AI synthesis confidence must be numeric.") from exc
    if not 0 <= confidence <= 1:
        raise AIProviderError("AI synthesis confidence must be between 0 and 1.")

    known_db = {str(item.get("ref")) for item in database_evidence}
    raw_db_refs = [str(value) for value in data.get("database_evidence_refs") or []]
    used_db = [ref for ref in raw_db_refs if ref in known_db]
    warnings: list[str] = []
    unknown_db = sorted(set(raw_db_refs) - known_db)
    if unknown_db:
        warnings.append("AI referenced unknown database evidence refs: " + ", ".join(unknown_db))
    if database_evidence and not used_db:
        warnings.append("AI did not explicitly reference supplied registry/database evidence in its structured result.")

    considerations = []
    for item in data.get("considerations") or []:
        if not isinstance(item, dict):
            continue
        item_db = [str(value) for value in item.get("database_evidence_refs") or []]
        considerations.append({
            "finding": str(item.get("finding") or ""),
            "basis": str(item.get("basis") or "model_reasoning"),
            "risk_effect": str(item.get("risk_effect") or "uncertain"),
            "database_evidence_refs": [ref for ref in item_db if ref in known_db],
        })

    return {
        "assessed": level != "unassessed",
        "semantic_level": None if level == "unassessed" else level,
        "semantic_label": None if level == "unassessed" else policy.level_by_id[level].label,
        "confidence": confidence,
        "method": "ai_capability_driven_synthesis",
        "ai_assisted": True,
        "rationale": str(data.get("rationale") or ""),
        "database_evidence_refs": used_db,
        "considerations": considerations,
        "config_rules_considered": [str(value) for value in data.get("config_rules_considered") or []],
        "governed_baseline_relation": str(data.get("governed_baseline_relation") or "not_comparable"),
        "uncertainty": str(data.get("uncertainty") or ""),
        "quality_warnings": warnings,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
    }


def synthesize_with_capabilities(
    provider: AIProvider,
    *,
    format_context: dict[str, Any],
    policy: SynthesisPolicy,
    governed_synthesis: dict[str, Any],
    risk_assessments: list[dict[str, Any]],
    criterion_claims: list[dict[str, Any]],
    source_evidence: list[dict[str, Any]],
    framework: Any | None = None,
    max_evidence_items: int = 100,
) -> dict[str, Any]:
    """Ask the AI client once, exposing provider capabilities when supported.

    The complete registry evidence, governed baseline, synthesis policy, and
    framework are supplied in one request. Azure/OpenAI providers that implement
    ``generate_with_capabilities`` may expose web search with automatic tool choice
    inside that same request; other providers fall back to their normal generation
    method. The AI output remains advisory and is never written to MongoDB here.
    """
    database_evidence = build_synthesis_evidence(
        risk_assessments=[dict(item) for item in risk_assessments if isinstance(item, dict)],
        criterion_claims=[dict(item) for item in criterion_claims if isinstance(item, dict)],
        source_evidence=[dict(item) for item in source_evidence if isinstance(item, dict)],
        policy=policy,
        max_items=max_evidence_items,
    )
    capabilities_available = provider.describe().get("capabilities") or {}
    synthesis_context = {
        "format": _safe(format_context),
        "registry_database_evidence": _safe(database_evidence),
        "governed_config_synthesis": _safe(governed_synthesis),
        "synthesis_policy": _safe(policy.raw),
        "assessment_framework": _safe(_framework_summary(framework)),
        "capabilities_available": _safe(capabilities_available),
    }
    request = AIRequest(
        messages=(
            AIMessage("system", AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Using the supplied evidence, methodology, deterministic baseline, and any capabilities available "
                "to you, return your synthesized preservation-risk analysis. The deterministic baseline is context, "
                "not a required answer: if you differ, explain why. If you obtain information externally, distinguish "
                "it clearly from supplied registry evidence. Do not invent evidence for missing sources.\n\n"
                + json.dumps(synthesis_context, indent=2, sort_keys=True, default=str),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_ai_synthesis",
        temperature=0.0,
    )

    capability_generate = getattr(provider, "generate_with_capabilities", None)
    if callable(capability_generate):
        response = capability_generate(request)
    else:
        response = provider.generate(request)

    overall = _validate_with_warnings(response, database_evidence=database_evidence, policy=policy)
    response_meta = response.metadata if isinstance(response.metadata, dict) else {}
    external_sources = [
        {
            "ref": f"W{index:03d}",
            "url": str(item.get("url") or ""),
            "title": item.get("title"),
        }
        for index, item in enumerate(response_meta.get("external_sources") or [], start=1)
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    web_search_used = bool(response_meta.get("web_search_used"))
    overall["governed_baseline"] = _safe(governed_synthesis)
    overall["capabilities_available"] = _safe(capabilities_available)
    overall["capabilities_used"] = {"web_search": web_search_used}
    overall["external_sources"] = external_sources

    return {
        "status": "ok",
        "mode": "capability_driven_ai_synthesis",
        "governed_synthesis": governed_synthesis,
        "overall_synthesized_risk": overall,
        "database_evidence_refs": database_evidence,
        "external_capability": {
            "capability_available": bool(capabilities_available.get("web_search")),
            "capability_invoked": bool(response_meta.get("responses_api")),
            "web_search_used": web_search_used,
            "search_queries": list(response_meta.get("search_queries") or []),
            "consulted_urls": list(response_meta.get("consulted_urls") or []),
            "sources": external_sources,
            "error": None,
        },
        "provider": provider.describe(),
        "usage": response.to_dict()["usage"],
        "authority_boundary": (
            "The AI-assisted result is returned for the consumer to evaluate. Source-native registry evidence and "
            "the deterministic/config synthesis remain unchanged and separately auditable; AI output is not written "
            "to MongoDB automatically."
        ),
    }


def synthesize_with_web_research(*args, **kwargs):
    """Compatibility alias retained for callers using the former function name."""
    return synthesize_with_capabilities(*args, **kwargs)
