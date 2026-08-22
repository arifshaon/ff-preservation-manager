from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


AI_RESEARCH_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the research-assisted synthesis component of a digital-preservation risk system. Registry evidence "
    "and the configured QNL policy are the starting point. Do not produce an independent preservation opinion from "
    "scratch. Use supplied web-grounded research only to verify, challenge, update, or supplement registry evidence. "
    "Never change a source-native assessment or configured source mapping. Missing database evidence is not a risk "
    "signal. Never numerically average heterogeneous source scales. Keep database evidence and web findings distinct "
    "and cite them only with reference IDs supplied by the application."
)


def _safe(value: Any, *, max_string: int = 5000) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "…"
    if isinstance(value, dict):
        return {str(key): _safe(item, max_string=max_string) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, max_string=max_string) for item in list(value)[:120]]
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


def _public_governed_summary(governed: dict[str, Any]) -> dict[str, Any]:
    """Keep only public/global baseline details in the web-grounding prompt."""
    summary_keys = (
        "assessed", "semantic_level", "semantic_label", "method", "basis", "policy_id", "policy_version",
        "missing_evidence_policy", "numeric_aggregation", "same_scope_aggregation", "broader_scope_policy",
    )
    result = {key: _safe(governed.get(key)) for key in summary_keys if governed.get(key) is not None}
    result["contributors"] = _safe(_public_evidence([
        item for item in governed.get("contributors") or [] if isinstance(item, dict)
    ]))
    result["contextual_contributors"] = _safe(_public_evidence([
        item for item in governed.get("contextual_contributors") or [] if isinstance(item, dict)
    ]))
    public_scopes = [
        str(scope) for scope in governed.get("selected_scope_types") or []
        if str(scope).strip().lower() != "institutional_format"
    ]
    if public_scopes:
        result["selected_scope_types"] = public_scopes
    return result


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


def _research_prompt(
    *,
    format_context: dict[str, Any],
    policy: SynthesisPolicy,
    governed_synthesis: dict[str, Any],
    database_evidence: list[dict[str, Any]],
    framework: Any | None,
) -> str:
    context = {
        "format": _public_format_context(format_context),
        "governed_config_synthesis": _public_governed_summary(governed_synthesis),
        "database_evidence": _safe(database_evidence),
        "assessment_framework": _safe(_framework_summary(framework)),
        "web_research_policy": _safe((policy.ai or {}).get("web_research") or {}),
    }
    return (
        "Perform targeted public-web research to VERIFY AND SUPPLEMENT the supplied preservation evidence for the "
        "resolved file format. Do not search for a generic overall 'risk score' and do not start a new assessment "
        "without the supplied evidence. First check current or authoritative information relevant to claims already "
        "in the database; then investigate material preservation factors not covered there. Prefer standards bodies, "
        "specification owners, official software/tool projects, national archives/libraries, preservation "
        "organizations, and authoritative technical documentation.\n\n"
        "For each material finding, say whether it CONFIRMS, CONTRADICTS, UPDATES/QUALIFIES, or SUPPLEMENTS the "
        "database evidence and explain preservation relevance. Check source currentness; specification disclosure and "
        "governance; current software/open-source tooling; adoption/community support; dependencies/external assets; "
        "migration pathways; IP/DRM constraints; and metadata/self-documentation. Absence of search results is not "
        "Low risk. Preserve source-native ratings exactly.\n\n"
        "Only public/global format evidence is supplied. Do not infer, search for, or discuss internal institutional "
        "capability, policy, storage, readiness, or other private operational information. Include concrete current "
        "facts and citations for the grounded synthesis step.\n\n"
        + json.dumps(context, indent=2, sort_keys=True, default=str)
    )


def _response_schema(policy: SynthesisPolicy) -> dict[str, Any]:
    levels = list(policy.level_by_id)
    finding = {
        "type": "object",
        "properties": {
            "finding": {"type": "string"},
            "relationship_to_database": {
                "type": "string",
                "enum": ["confirms", "contradicts", "qualifies_or_updates", "supplements", "unclear"],
            },
            "risk_effect": {
                "type": "string",
                "enum": ["raises_concern", "reduces_concern", "neutral", "uncertain"],
            },
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "web_source_refs": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": [
            "finding", "relationship_to_database", "risk_effect",
            "database_evidence_refs", "web_source_refs", "rationale",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "semantic_level": {"type": "string", "enum": levels + ["unassessed"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "web_source_refs": {"type": "array", "items": {"type": "string"}},
            "verification_findings": {"type": "array", "items": finding},
            "policy_rules_applied": {"type": "array", "items": {"type": "string"}},
            "governed_baseline_relation": {
                "type": "string",
                "enum": ["same", "higher_concern", "lower_concern", "not_comparable"],
            },
            "uncertainty": {"type": "string"},
        },
        "required": [
            "semantic_level", "confidence", "rationale", "database_evidence_refs", "web_source_refs",
            "verification_findings", "policy_rules_applied", "governed_baseline_relation", "uncertainty",
        ],
        "additionalProperties": False,
    }


def _validate_synthesis(
    response: AIResponse,
    *,
    database_evidence: list[dict[str, Any]],
    web_sources: list[dict[str, Any]],
    policy: SynthesisPolicy,
) -> dict[str, Any]:
    data = response.structured
    if not isinstance(data, dict):
        raise AIProviderError("AI researched synthesis did not return a structured JSON object.")

    allowed_levels = set(policy.level_by_id) | {"unassessed"}
    level = str(data.get("semantic_level") or "")
    if level not in allowed_levels:
        raise AIProviderError(f"AI researched synthesis returned unsupported level '{level}'.")
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIProviderError("AI researched synthesis confidence must be numeric.") from exc
    if not 0 <= confidence <= 1:
        raise AIProviderError("AI researched synthesis confidence must be between 0 and 1.")

    db_refs = {str(item.get("ref")) for item in database_evidence}
    web_refs = {str(item.get("ref")) for item in web_sources}
    used_db = [str(value) for value in data.get("database_evidence_refs") or []]
    used_web = [str(value) for value in data.get("web_source_refs") or []]
    if set(used_db) - db_refs:
        raise AIProviderError("AI researched synthesis cited unknown database refs.")
    if set(used_web) - web_refs:
        raise AIProviderError("AI researched synthesis cited unknown web refs.")
    if level != "unassessed":
        if database_evidence and not used_db:
            raise AIProviderError(
                "An assessed researched synthesis must cite registry/database evidence when it is available."
            )
        if not used_web:
            raise AIProviderError(
                "An assessed researched synthesis must cite web evidence because web research is enabled."
            )

    findings = []
    for item in data.get("verification_findings") or []:
        if not isinstance(item, dict):
            raise AIProviderError("verification_findings entries must be objects.")
        finding_db = [str(value) for value in item.get("database_evidence_refs") or []]
        finding_web = [str(value) for value in item.get("web_source_refs") or []]
        if set(finding_db) - db_refs or set(finding_web) - web_refs:
            raise AIProviderError("AI researched synthesis finding cites unknown evidence refs.")
        findings.append({
            "finding": str(item.get("finding") or ""),
            "relationship_to_database": str(item.get("relationship_to_database") or "unclear"),
            "risk_effect": str(item.get("risk_effect") or "uncertain"),
            "database_evidence_refs": finding_db,
            "web_source_refs": finding_web,
            "rationale": str(item.get("rationale") or ""),
        })

    return {
        "assessed": level != "unassessed",
        "semantic_level": None if level == "unassessed" else level,
        "semantic_label": None if level == "unassessed" else policy.level_by_id[level].label,
        "confidence": confidence,
        "method": "ai_web_research_assisted_synthesis",
        "ai_assisted": True,
        "web_researched": True,
        "rationale": str(data.get("rationale") or ""),
        "database_evidence_refs": used_db,
        "web_source_refs": used_web,
        "verification_findings": findings,
        "policy_rules_applied": [str(value) for value in data.get("policy_rules_applied") or []],
        "governed_baseline_relation": str(data.get("governed_baseline_relation") or "not_comparable"),
        "uncertainty": str(data.get("uncertainty") or ""),
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
        "missing_evidence_policy": policy.synthesis["missing_assessment_policy"],
        "numeric_aggregation": policy.synthesis["numeric_aggregation"],
    }


def synthesize_with_web_research(
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
    """Verify/supplement public registry evidence on the web, then synthesize.

    Institution-scoped evidence is excluded before web grounding. Source-native
    assessments remain immutable and researched findings are not written to MongoDB.
    """
    web_policy = (policy.ai or {}).get("web_research") or {}
    if not web_policy.get("require_web_grounding", True):
        raise AIProviderError("Web-researched synthesis requires web grounding by policy.")
    if not provider.capabilities.web_search:
        raise AIProviderError(f"AI provider '{provider.provider_name}' does not support web search.")

    public_risk = _public_evidence(risk_assessments)
    public_claims = _public_evidence(criterion_claims)
    public_source = _public_evidence(source_evidence)
    excluded_private_count = (
        len(risk_assessments) - len(public_risk)
        + len(criterion_claims) - len(public_claims)
        + len(source_evidence) - len(public_source)
    )
    database_evidence = build_synthesis_evidence(
        risk_assessments=public_risk,
        criterion_claims=public_claims,
        source_evidence=public_source,
        policy=policy,
        max_items=max_evidence_items,
    )

    research = provider.research_web(_research_prompt(
        format_context=format_context,
        policy=policy,
        governed_synthesis=governed_synthesis,
        database_evidence=database_evidence,
        framework=framework,
    ))
    citations = [
        {"ref": f"W{index:03d}", "url": citation.url, "title": citation.title}
        for index, citation in enumerate(research.citations, start=1)
    ]
    if web_policy.get("require_citations", True) and not citations:
        raise AIProviderError("Web-researched synthesis requires cited web sources, but none were returned.")

    synthesis_context = {
        "format": _public_format_context(format_context),
        "governed_config_synthesis": _safe(governed_synthesis),
        "synthesis_policy": _safe(policy.raw),
        "assessment_framework": _safe(_framework_summary(framework)),
        "database_evidence": _safe(database_evidence),
        "web_research_report": research.text,
        "web_sources": citations,
        "search_queries": list(research.search_queries),
        "instructions": {
            "registry_evidence_is_primary_input": True,
            "assessed_result_must_use_registry_evidence_when_available": True,
            "web_research_role": "verify_and_supplement",
            "configured_source_mappings_are_binding": True,
            "native_source_assessments_are_immutable": True,
            "missing_database_evidence_is_not_low_risk": True,
            "generic_independent_risk_analysis_forbidden": True,
            "web_findings_must_be_cited": True,
            "institution_scoped_evidence_excluded_from_web_grounding": True,
        },
    }
    response = provider.generate(AIRequest(
        messages=(
            AIMessage("system", AI_RESEARCH_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Using registry evidence as the primary evidence base and the grounded web report only as "
                "verification/supplementary evidence, produce the final AI-assisted preservation-risk synthesis. "
                "An assessed result must cite registry evidence whenever any is supplied, and must cite the web "
                "evidence used for verification. Explain confirmations, contradictions, updates, or additions. "
                "Apply configured QNL rules and do not modify source-native ratings or mappings.\n\n"
                + json.dumps(synthesis_context, indent=2, sort_keys=True, default=str),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_researched_synthesis",
        temperature=0.0,
    ))
    overall = _validate_synthesis(
        response,
        database_evidence=database_evidence,
        web_sources=citations,
        policy=policy,
    )
    overall["governed_baseline"] = _safe(governed_synthesis)

    return {
        "status": "ok",
        "mode": "registry_first_web_research",
        "governed_synthesis": governed_synthesis,
        "overall_synthesized_risk": overall,
        "database_evidence_refs": database_evidence,
        "web_research": {
            "report": research.text,
            "citations": citations,
            "search_queries": list(research.search_queries),
            "consulted_urls": list(research.consulted_urls),
            "provider": research.provider,
            "model": research.model,
            "usage": research.to_dict()["usage"],
            "persisted": False,
            "institution_scoped_evidence_excluded": excluded_private_count,
        },
        "provider": provider.describe(),
        "authority_boundary": (
            "The AI-assisted result begins with collected public/global registry evidence and configured mappings. "
            "An assessed researched result must use registry evidence when available and cited public-web evidence. "
            "Public-web research only verifies, qualifies, or supplements the registry evidence. Institution-scoped "
            "evidence is not sent to public web grounding. Source-native ratings and configured mappings are not "
            "rewritten, missing evidence contributes nothing, and researched findings are not persisted."
        ),
    }
