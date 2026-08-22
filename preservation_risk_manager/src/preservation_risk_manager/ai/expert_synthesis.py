from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


AI_EXPERT_SYNTHESIS_SYSTEM_PROMPT = (
    "You are an expert digital-preservation risk analyst. Produce an independent advisory preservation-risk "
    "assessment for the resolved file format. You may use both the supplied registry evidence and your broader "
    "trained model knowledge about file formats, standards, software ecosystems, adoption, obsolescence, migration, "
    "rendering dependencies, intellectual-property constraints, and preservation practice. The configured QNL "
    "synthesis policy and governed result must be considered, but your expert conclusion may differ from the "
    "governed result when broader knowledge supports a different conclusion. Never change or misstate a source's "
    "native assessment or configured semantic mapping. Keep registry-derived evidence and model-knowledge findings "
    "clearly separate. Missing database evidence is not Low risk. Do not claim live web verification or current "
    "external verification: your broader knowledge comes from model training and may be stale. If the available "
    "information is insufficient for a responsible conclusion, return semantic_level='unassessed'."
)


def _safe(value: Any, *, max_string: int = 3500) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "…"
    if isinstance(value, dict):
        return {str(key): _safe(item, max_string=max_string) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, max_string=max_string) for item in list(value)[:100]]
    return _safe(str(value), max_string=max_string)


def _response_schema(policy: SynthesisPolicy) -> dict[str, Any]:
    levels = [level.id for level in policy.semantic_levels]
    return {
        "type": "object",
        "properties": {
            "semantic_level": {"type": "string", "enum": levels + ["unassessed"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "database_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "model_knowledge_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "finding": {"type": "string"},
                        "risk_effect": {
                            "type": "string",
                            "enum": ["raises_concern", "reduces_concern", "neutral", "uncertain"],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "temporal_sensitivity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["finding", "risk_effect", "confidence", "temporal_sensitivity"],
                    "additionalProperties": False,
                },
            },
            "config_rules_considered": {"type": "array", "items": {"type": "string"}},
            "divergence_explanation": {"type": "string"},
            "uncertainty": {"type": "string"},
        },
        "required": [
            "semantic_level",
            "confidence",
            "rationale",
            "database_evidence_refs",
            "model_knowledge_findings",
            "config_rules_considered",
            "divergence_explanation",
            "uncertainty",
        ],
        "additionalProperties": False,
    }


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
        })
    return {
        "framework_id": getattr(framework, "framework_id", None),
        "version": getattr(framework, "version", None),
        "calibration_status": getattr(framework, "calibration_status", None),
        "questions": questions,
    }


def _compare_levels(policy: SynthesisPolicy, governed: dict[str, Any], expert_level: str) -> dict[str, Any]:
    governed_level = str(governed.get("semantic_level") or "")
    if expert_level == "unassessed" or governed_level not in policy.rank_by_level:
        relation = "not_comparable"
    elif expert_level == governed_level:
        relation = "agrees"
    elif policy.rank_by_level[expert_level] > policy.rank_by_level[governed_level]:
        relation = "ai_more_concerned"
    else:
        relation = "ai_less_concerned"
    return {
        "governed_semantic_level": governed_level or None,
        "ai_semantic_level": None if expert_level == "unassessed" else expert_level,
        "relation": relation,
    }


def _validate_response(
    response: AIResponse,
    *,
    evidence: list[dict[str, Any]],
    policy: SynthesisPolicy,
    governed: dict[str, Any],
) -> dict[str, Any]:
    data = response.structured
    if not isinstance(data, dict):
        raise AIProviderError("AI expert synthesis did not return a structured JSON object.")

    allowed_levels = set(policy.level_by_id) | {"unassessed"}
    level = str(data.get("semantic_level") or "")
    if level not in allowed_levels:
        raise AIProviderError(f"AI expert synthesis returned unsupported semantic level '{level}'.")
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIProviderError("AI expert synthesis confidence must be numeric.") from exc
    if not 0 <= confidence <= 1:
        raise AIProviderError("AI expert synthesis confidence must be between 0 and 1.")

    known_refs = {str(item.get("ref")) for item in evidence}
    refs = [str(value) for value in data.get("database_evidence_refs") or []]
    unknown_refs = sorted(set(refs) - known_refs)
    if unknown_refs:
        raise AIProviderError(
            "AI expert synthesis cited unknown database evidence refs: " + ", ".join(unknown_refs)
        )

    findings: list[dict[str, Any]] = []
    for item in data.get("model_knowledge_findings") or []:
        if not isinstance(item, dict):
            raise AIProviderError("model_knowledge_findings entries must be objects.")
        try:
            item_confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise AIProviderError("Model-knowledge finding confidence must be numeric.") from exc
        if not 0 <= item_confidence <= 1:
            raise AIProviderError("Model-knowledge finding confidence must be between 0 and 1.")
        findings.append({
            "finding": str(item.get("finding") or ""),
            "risk_effect": str(item.get("risk_effect") or "uncertain"),
            "confidence": item_confidence,
            "temporal_sensitivity": str(item.get("temporal_sensitivity") or "high"),
        })

    comparison = _compare_levels(policy, governed, level)
    return {
        "assessed": level != "unassessed",
        "semantic_level": None if level == "unassessed" else level,
        "semantic_label": None if level == "unassessed" else policy.level_by_id[level].label,
        "confidence": confidence,
        "method": "ai_expert_synthesis_model_knowledge",
        "advisory": True,
        "authoritative": False,
        "knowledge_basis": "supplied_registry_evidence_plus_model_training_knowledge",
        "live_web_verified": False,
        "rationale": str(data.get("rationale") or ""),
        "database_evidence_refs": refs,
        "model_knowledge_findings": findings,
        "config_rules_considered": [str(value) for value in data.get("config_rules_considered") or []],
        "divergence_explanation": str(data.get("divergence_explanation") or ""),
        "uncertainty": str(data.get("uncertainty") or ""),
        "comparison_to_governed": comparison,
        "provider": response.provider,
        "model": response.model,
        "usage": response.to_dict()["usage"],
        "currentness_caveat": (
            "This AI expert assessment may use broader model-trained knowledge, but it did not perform live web "
            "verification. Time-sensitive ecosystem, software-support, and standards facts may therefore be stale."
        ),
    }


def synthesize_expert_with_ai(
    provider: AIProvider,
    *,
    format_context: dict[str, Any],
    policy: SynthesisPolicy,
    governed_synthesis: dict[str, Any],
    risk_assessments: list[dict[str, Any]],
    criterion_claims: list[dict[str, Any]],
    source_evidence: list[dict[str, Any]],
    framework: Any | None = None,
    max_evidence_items: int = 120,
) -> dict[str, Any]:
    """Return a parallel AI expert opinion using registry evidence plus model knowledge.

    The governed/config-driven synthesis is never overwritten. This function is
    intentionally different from bounded ``synthesize_with_ai``: broader trained
    model knowledge is allowed, but must be disclosed separately from registry
    evidence and is never presented as live external verification.
    """
    evidence = build_synthesis_evidence(
        risk_assessments=risk_assessments,
        criterion_claims=criterion_claims,
        source_evidence=source_evidence,
        policy=policy,
        max_items=max_evidence_items,
    )
    expert_policy = (policy.ai or {}).get("expert_synthesis") or {}
    context = {
        "format": _safe(format_context),
        "governed_synthesis": _safe(governed_synthesis),
        "synthesis_policy": _safe(policy.raw),
        "expert_synthesis_policy": _safe(expert_policy),
        "assessment_framework": _safe(_framework_summary(framework)),
        "database_evidence": evidence,
        "instructions": {
            "produce_parallel_advisory_result": True,
            "may_disagree_with_governed_result": True,
            "must_consider_configured_rules": True,
            "must_preserve_source_native_and_configured_mappings": True,
            "model_training_knowledge_allowed": True,
            "live_web_verification_available": False,
            "separate_database_evidence_from_model_knowledge": True,
            "missing_database_evidence_is_not_low_risk": True,
        },
    }
    request = AIRequest(
        messages=(
            AIMessage("system", AI_EXPERT_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                "Provide an independent expert preservation-risk synthesis for this format. Consider the governed "
                "result and rules, but also use relevant broader trained knowledge. Explain any disagreement. "
                "Reference supplied database evidence only through its R/C/S refs; put broader knowledge only in "
                "model_knowledge_findings.\n\n" + json.dumps(context, indent=2, sort_keys=True, default=str),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_expert_synthesis",
        temperature=0.0,
    )
    response = provider.generate(request)
    expert = _validate_response(response, evidence=evidence, policy=policy, governed=governed_synthesis)
    return {
        "status": "ok",
        "governed_synthesis": governed_synthesis,
        "ai_expert_synthesized_risk": expert,
        "evidence_refs": evidence,
        "authority_boundary": (
            "The governed config-driven synthesis remains the auditable institutional result. The AI expert "
            "synthesis is a parallel advisory opinion that may use model-trained knowledge and may disagree; it "
            "does not modify registry data, source mappings, or the governed result."
        ),
    }
