from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT = (
    "You are assisting with a digital-preservation risk assessment. The application supplies the resolved format, "
    "its collected registry/source evidence, the configured deterministic synthesis, the QNL synthesis policy, and "
    "the assessment framework. Treat all of that as important context. Produce an AI-assisted synthesized preservation "
    "risk using your available capabilities. You may use additional external information when it is useful and "
    "available, but do not misattribute external information to NARA, DPC, LOC, PRONOM, or another supplied source. "
    "Preserve source-native statements as source statements. Missing evidence is not Low risk. Explain material "
    "agreement or disagreement with the governed/config baseline, and report confidence and uncertainty."
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


def _is_institution_scoped(item: dict[str, Any]) -> bool:
    if item.get("institution_id"):
        return True
    if str(item.get("source_independence") or "").strip().lower() == "institution_scoped":
        return True
    return str(item.get("scope_type") or "").strip().lower() == "institutional_format"


def _public_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in items if isinstance(item, dict) and not _is_institution_scoped(item)]


def _public_format_context(format_context: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "canonical_id", "format_id", "preferred_name", "format_name", "name", "label",
        "version", "versions", "puids", "loc_ids", "nara_ids", "extensions", "mime_types",
        "internal_signature_names", "identifiers",
    )
    return {key: _safe(format_context.get(key)) for key in allowed if format_context.get(key) is not None}


def _framework_summary(framework: Any | None) -> dict[str, Any] | None:
    if framework is None:
        return None
    questions = []
    for question in getattr(framework, "questions", ()):
        questions.append({
            "question_id": getattr(question, "id", None),
            "label": getattr(question, "label", None),
            "domain_id": getattr(question, "domain_id", None),
            "domain_label": getattr(question, "domain_label", None),
            "critical": bool(getattr(question, "critical", False)),
            "evidence_fields": list(getattr(question, "evidence_fields", ()) or ()),
            "applicability": list(getattr(question, "applicability", ()) or ()),
        })
    return {
        "framework_id": getattr(framework, "framework_id", None),
        "version": getattr(framework, "version", None),
        "calibration_status": getattr(framework, "calibration_status", None),
        "questions": questions,
    }


def _capability_prompt(
    *,
    format_context: dict[str, Any],
    governed_synthesis: dict[str, Any],
    database_evidence: list[dict[str, Any]],
    framework: Any | None,
    policy: SynthesisPolicy,
) -> str:
    context = {
        "format": _public_format_context(format_context),
        "governed_config_synthesis": _safe(governed_synthesis),
        "database_evidence": _safe(database_evidence),
        "assessment_framework": _safe(_framework_summary(framework)),
        "synthesis_policy": _safe(policy.raw),
    }
    return (
        "Here is the preservation-risk context assembled by the application. Analyse it using the capabilities "
        "available to you. If external/web search is useful, you may use it; if it is not useful or unavailable, "
        "continue with the supplied context. Do not ignore the supplied source evidence or deterministic baseline. "
        "If you use information from outside the supplied evidence, make that clear so it can be distinguished from "
        "registry evidence. Return a concise analytical report that can be passed into a structured synthesis step.\n\n"
        + json.dumps(context, indent=2, sort_keys=True, default=str)
    )


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
            "external_source_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["finding", "basis", "risk_effect", "database_evidence_refs", "external_source_refs"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "semantic_level": {"type": "string", "enum": levels + ["unassessed"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "external_source_refs": {"type": "array", "items": {"type": "string"}},
            "considerations": {"type": "array", "items": consideration},
            "config_rules_considered": {"type": "array", "items": {"type": "string"}},
            "governed_baseline_relation": {
                "type": "string",
                "enum": ["same", "higher_concern", "lower_concern", "not_comparable"],
            },
            "uncertainty": {"type": "string"},
        },
        "required": [
            "semantic_level", "confidence", "rationale", "database_evidence_refs", "external_source_refs",
            "considerations", "config_rules_considered", "governed_baseline_relation", "uncertainty",
        ],
        "additionalProperties": False,
    }


def _validate_with_warnings(
    response: AIResponse,
    *,
    database_evidence: list[dict[str, Any]],
    external_sources: list[dict[str, Any]],
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
    known_external = {str(item.get("ref")) for item in external_sources}
    raw_db_refs = [str(value) for value in data.get("database_evidence_refs") or []]
    raw_external_refs = [str(value) for value in data.get("external_source_refs") or []]
    used_db = [ref for ref in raw_db_refs if ref in known_db]
    used_external = [ref for ref in raw_external_refs if ref in known_external]
    warnings: list[str] = []
    unknown_db = sorted(set(raw_db_refs) - known_db)
    unknown_external = sorted(set(raw_external_refs) - known_external)
    if unknown_db:
        warnings.append("AI referenced unknown database evidence refs: " + ", ".join(unknown_db))
    if unknown_external:
        warnings.append("AI referenced unknown external source refs: " + ", ".join(unknown_external))
    if database_evidence and not used_db:
        warnings.append("AI did not explicitly reference supplied registry/database evidence in its structured result.")

    considerations: list[dict[str, Any]] = []
    for item in data.get("considerations") or []:
        if not isinstance(item, dict):
            continue
        item_db = [str(value) for value in item.get("database_evidence_refs") or []]
        item_external = [str(value) for value in item.get("external_source_refs") or []]
        considerations.append({
            "finding": str(item.get("finding") or ""),
            "basis": str(item.get("basis") or "model_reasoning"),
            "risk_effect": str(item.get("risk_effect") or "uncertain"),
            "database_evidence_refs": [ref for ref in item_db if ref in known_db],
            "external_source_refs": [ref for ref in item_external if ref in known_external],
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
        "external_source_refs": used_external,
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
    """Produce one AI-assisted synthesis from application context and provider capabilities.

    The application supplies evidence and methodology. It does not require a
    particular research sequence. When the provider exposes web search, that
    capability is made available with provider-side automatic tool choice. The
    provider/model may use it or decline it. Failure or absence of external search
    does not prevent the AI from analysing the supplied registry evidence.
    """
    database_evidence = build_synthesis_evidence(
        risk_assessments=[dict(item) for item in risk_assessments if isinstance(item, dict)],
        criterion_claims=[dict(item) for item in criterion_claims if isinstance(item, dict)],
        source_evidence=[dict(item) for item in source_evidence if isinstance(item, dict)],
        policy=policy,
        max_items=max_evidence_items,
    )

    capabilities_available = provider.describe().get("capabilities") or {}
    external_report = ""
    external_sources: list[dict[str, Any]] = []
    external_metadata: dict[str, Any] = {
        "capability_available": bool(capabilities_available.get("web_search")),
        "capability_invoked": False,
        "web_search_used": False,
        "error": None,
    }

    if capabilities_available.get("web_search"):
        public_risk = _public_evidence(risk_assessments)
        public_claims = _public_evidence(criterion_claims)
        public_source = _public_evidence(source_evidence)
        public_database_evidence = build_synthesis_evidence(
            risk_assessments=public_risk,
            criterion_claims=public_claims,
            source_evidence=public_source,
            policy=policy,
            max_items=max_evidence_items,
        )
        try:
            external = provider.research_web(
                _capability_prompt(
                    format_context=format_context,
                    governed_synthesis=governed_synthesis,
                    database_evidence=public_database_evidence,
                    framework=framework,
                    policy=policy,
                )
            )
            external_metadata["capability_invoked"] = True
            external_metadata["web_search_used"] = bool(external.metadata.get("web_search_used"))
            external_metadata["search_queries"] = list(external.search_queries)
            external_metadata["consulted_urls"] = list(external.consulted_urls)
            external_report = external.text
            external_sources = [
                {"ref": f"W{index:03d}", "url": citation.url, "title": citation.title}
                for index, citation in enumerate(external.citations, start=1)
            ]
            external_metadata["sources"] = external_sources
            external_metadata["usage"] = external.to_dict()["usage"]
        except Exception as exc:
            external_metadata["capability_invoked"] = True
            external_metadata["error"] = f"{type(exc).__name__}: {exc}"

    synthesis_context = {
        "format": _safe(format_context),
        "registry_database_evidence": _safe(database_evidence),
        "governed_config_synthesis": _safe(governed_synthesis),
        "synthesis_policy": _safe(policy.raw),
        "assessment_framework": _safe(_framework_summary(framework)),
        "capabilities_available": _safe(capabilities_available),
        "external_capability_result": {
            "web_search_used": external_metadata.get("web_search_used"),
            "report": external_report,
            "sources": external_sources,
            "error": external_metadata.get("error"),
        },
    }
    request = AIRequest(
        messages=(
            AIMessage("system", AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Using the supplied evidence, methodology, deterministic baseline, and any additional capability "
                "results available to you, return your synthesized preservation-risk analysis. The deterministic "
                "baseline is context, not a required answer: if you differ, explain why. Clearly distinguish supplied "
                "registry evidence from external information or your own analytical reasoning.\n\n"
                + json.dumps(synthesis_context, indent=2, sort_keys=True, default=str),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_ai_synthesis",
        temperature=0.0,
    )
    response = provider.generate(request)
    overall = _validate_with_warnings(
        response,
        database_evidence=database_evidence,
        external_sources=external_sources,
        policy=policy,
    )
    overall["governed_baseline"] = _safe(governed_synthesis)
    overall["capabilities_available"] = _safe(capabilities_available)
    overall["capabilities_used"] = {
        "web_search": bool(external_metadata.get("web_search_used")),
    }

    return {
        "status": "ok",
        "mode": "capability_driven_ai_synthesis",
        "governed_synthesis": governed_synthesis,
        "overall_synthesized_risk": overall,
        "database_evidence_refs": database_evidence,
        "external_capability": external_metadata,
        "provider": provider.describe(),
        "authority_boundary": (
            "The AI-assisted result is returned for the consumer to evaluate. Source-native registry evidence and "
            "the deterministic/config synthesis remain unchanged and separately auditable; AI output is not written "
            "to MongoDB automatically."
        ),
    }


def synthesize_with_web_research(*args, **kwargs):
    """Compatibility alias for the former explicitly web-researched workflow."""
    return synthesize_with_capabilities(*args, **kwargs)
