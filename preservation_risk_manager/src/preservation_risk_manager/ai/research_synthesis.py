from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


AI_RESEARCH_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the research-assisted synthesis component of a digital-preservation risk system. The registry evidence "
    "and configured QNL policy are the starting point and must remain visible in the analysis. You are not producing "
    "an independent preservation opinion from scratch. Use the supplied web-grounded research only to verify, "
    "challenge, update, or supplement the supplied registry evidence. Never change a source's native assessment or "
    "configured source-to-semantic mapping. Missing database evidence is not a risk signal. Do not numerically "
    "average heterogeneous source scales. Distinguish database evidence from web research and cite both by the "
    "reference IDs supplied by the application."
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
    return str(item.get("source_independence") or "").strip().lower() == "institution_scoped"


def _public_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude institution/private evidence before invoking public web grounding."""
    return [dict(item) for item in items if isinstance(item, dict) and not _is_institution_scoped(item)]


def _public_format_context(format_context: dict[str, Any]) -> dict[str, Any]:
    """Send only format identity fields to the external web-grounding service."""
    allowed = (
        "canonical_id",
        "format_id",
        "preferred_name",
        "format_name",
        "name",
        "label",
        "version",
        "versions",
        "puids",
        "loc_ids",
        "nara_ids",
        "extensions",
        "mime_types",
        "internal_signature_names",
        "identifiers",
    )
    return {key: _safe(format_context.get(key)) for key in allowed if format_context.get(key) is not None}


def _framework_summary(framework: Any | None) -> dict[str, Any] | None:
    if framework is None:
        return None
    questions: list[dict[str, Any]] = []
    for question in getattr(framework, "questions", ()):
        # Only public question metadata is sent; no institution-specific answers
        # or local evidence are included in the web-grounding payload.
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
    web_policy = (policy.ai or {}).get("web_research") or {}
    context = {
        "format": _public_format_context(format_context),
        "governed_config_synthesis": _safe(governed_synthesis),
        "database_evidence": _safe(database_evidence),
        "assessment_framework": _safe(_framework_summary(framework)),
        "web_research_policy": _safe(web_policy),
    }
    return (
        "Perform targeted public-web research to VERIFY AND SUPPLEMENT the supplied preservation evidence for the "
        "resolved file format. Do not search for a generic overall 'risk score' and do not start a new assessment "
        "without the supplied evidence. First check current/authoritative information relevant to claims already in "
        "the database; then investigate material preservation factors that the database does not cover. Prefer "
        "primary sources such as standards bodies, specification owners, official software/tool projects, national "
        "archives/libraries, preservation organizations, and authoritative technical documentation.\n\n"
        "For each important finding, state whether it CONFIRMS, CONTRADICTS, UPDATES/QUALIFIES, or SUPPLEMENTS the "
        "database evidence, and explain its preservation relevance. Pay particular attention to: source accuracy and "
        "currentness; specification disclosure/governance; current software and open-source tooling; adoption and "
        "community support; dependencies/external assets; migration/conversion pathways; IP/DRM constraints; and "
        "metadata/self-documentation. Do not treat an absence of search results as Low risk. Preserve source-native "
        "ratings exactly as supplied.\n\n"
        "The supplied database evidence contains global/public format evidence only. Do not infer or seek internal "
        "institutional capability, policy, storage, or readiness information from the public web.\n\n"
        "The grounded report will later be used by a policy-guided synthesis step, so include concrete current facts "
        "and cite the web sources supporting them.\n\n" + json.dumps(context, indent=2, sort_keys=True, default=str)
    )


def _response_schema(policy: SynthesisPolicy) -> dict[str, Any]:
    levels = list(policy.level_by_id)
    return {
        "type": "object",
        "properties": {
            "semantic_level": {"type": "string", "enum": levels + ["unassessed"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "web_source_refs": {"type": "array", "items": {"type": "string"}},
            "verification_findings": {
                "type": "array",
                "items": {
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
                        "finding",
                        "relationship_to_database",
                        "risk_effect",
                        "database_evidence_refs",
                        "web_source_refs",
                        "rationale"
                    ],
                    "additionalProperties": False,
                }
            },
            "policy_rules_applied": {"type": "array", "items": {"type": "string"}},
            "governed_baseline_relation": {
                "type": "string",
                "enum": ["same", "higher_concern", "lower_concern", "not_comparable"]
            },
            "uncertainty": {"type": "string"}
        },
        "required": [
            "semantic_level",
            "confidence",
            "rationale",
            "database_evidence_refs",
            "web_source_refs",
            "verification_findings",
            "policy_rules_applied",
            "governed_baseline_relation",
            "uncertainty"
        ],
        "additionalProperties": False
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
    unknown_db = sorted(set(used_db) - db_refs)
    unknown_web = sorted(set(used_web) - web_refs)
    if unknown_db:
        raise AIProviderError("AI researched synthesis cited unknown database refs: " + ", ".join(unknown_db))
    if unknown_web:
        raise AIProviderError("AI researched synthesis cited unknown web refs: " + ", ".join(unknown_web))
    if level != "unassessed" and not (used_db or used_web):
        raise AIProviderError("An assessed researched synthesis must cite database or web evidence.")

    findings: list[dict[str, Any]] = []
    for item in data.get("verification_findings") or []:
        if not isinstance(item, dict):
            raise AIProviderError("verification_findings entries must be objects.")
        finding_db = [str(value) for value in item.get("database_evidence_refs") or []]
        finding_web = [str(value) for value in item.get("web_source_refs") or []]
        bad_db = sorted(set(finding_db) - db_refs)
        bad_web = sorted(set(finding_web) - web_refs)
        if bad_db or bad_web:
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

    The workflow is registry-first. It does not ask the model to independently
    assess a format from general knowledge. Public web search validates or
    supplements existing global/source evidence and retains URLs for audit.
    Institution-scoped evidence is excluded before web grounding. No research
    finding is persisted to MongoDB.
    """
    web_policy = (policy.ai or {}).get("web_research") or {}
    if not web_policy.get("require_web_grounding", True):
        raise AIProviderError("Web-researched synthesis requires web grounding by policy.")
    if not provider.capabilities.web_search:
        raise AIProviderError(f"AI provider '{provider.provider_name}' does not support web search.")

    public_risk_assessments = _public_evidence(risk_assessments)
    public_criterion_claims = _public_evidence(criterion_claims)
    public_source_evidence = _public_evidence(source_evidence)
    excluded_private_count = (
        (len(risk_assessments) - len(public_risk_assessments))
        + (len(criterion_claims) - len(public_criterion_claims))
        + (len(source_evidence) - len(public_source_evidence))
    )

    database_evidence = build_synthesis_evidence(
        risk_assessments=public_risk_assessments,
        criterion_claims=public_criterion_claims,
        source_evidence=public_source_evidence,
        policy=policy,
        max_items=max_evidence_items,
    )
    research = provider.research_web(
        _research_prompt(
            format_context=_public_format_context(format_context),
            policy=policy,
            governed_synthesis=governed_synthesis,
            database_evidence=database_evidence,
            framework=framework,
        )
    )
    citations = [
        {
            "ref": f"W{index:03d}",
            "url": citation.url,
            "title": citation.title,
        }
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
            "web_research_role": "verify_and_supplement",
            "configured_source_mappings_are_binding": True,
            "native_source_assessments_are_immutable": True,
            "missing_database_evidence_is_not_low_risk": True,
            "generic_independent_risk_analysis_forbidden": True,
            "web_findings_must_be_cited": True,
            "institution_scoped_evidence_excluded_from_web_grounding": True,
        },
    }
    request = AIRequest(
        messages=(
            AIMessage("system", AI_RESEARCH_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Using the supplied registry evidence as the primary evidence base and the grounded web report only "
                "as verification/supplementary evidence, produce the final AI-assisted preservation-risk synthesis. "
                "Explain material confirmations, contradictions, updates, or new evidence. Apply the configured QNL "
                "policy where relevant and do not modify source-native ratings or their configured mappings.\n\n"
                + json.dumps(synthesis_context, indent=2, sort_keys=True, default=str),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_researched_synthesis",
        temperature=0.0,
    )
    response = provider.generate(request)
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
            "The AI-assisted result begins with collected public/global registry evidence and configured source "
            "mappings. Public-web research is used only to verify, qualify, or supplement that evidence. "
            "Institution-scoped evidence is not sent to public web grounding. Source-native ratings and configured "
            "mappings are not rewritten, missing evidence contributes nothing, and researched findings are not "
            "persisted to the registry by this workflow."
        ),
    }
