from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse
from preservation_risk_manager.synthesis_policy import SynthesisPolicy, normalize_assessment, synthesize_assessments


AI_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the evidence-bounded synthesis component of a digital-preservation risk system. "
    "Use only the evidence supplied by the application. Never use general knowledge, memory, web knowledge, "
    "or unstated assumptions. The supplied synthesis policy is binding. Missing evidence contributes nothing. "
    "Do not treat absence of a source as Low risk. Do not numerically average heterogeneous source scales. "
    "Do not change a configured source mapping, declared source scope, or source-native value. You may interpret "
    "an explicit source-native risk assessment when no configured mapping can normalize it. Supporting evidence "
    "such as sustainability factors may inform a direct AI synthesis only when the policy permits and no mapped "
    "source-level assessment exists. Cite only evidence refs supplied by the application. If evidence cannot "
    "support an overall preservation-risk conclusion, return proposed_overall_level='unassessed'."
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


def build_synthesis_evidence(
    *,
    risk_assessments: list[dict[str, Any]],
    criterion_claims: list[dict[str, Any]],
    source_evidence: list[dict[str, Any]],
    policy: SynthesisPolicy,
    max_items: int = 80,
) -> list[dict[str, Any]]:
    """Create a bounded reference-addressable evidence bundle for AI synthesis."""
    max_items = max(1, int(max_items))
    refs: list[dict[str, Any]] = []

    for index, assessment in enumerate(risk_assessments, start=1):
        normalized = normalize_assessment(assessment, policy)
        refs.append({
            "ref": f"R{index:03d}",
            "kind": "governed_source_risk_assessment",
            "evidence": _safe(normalized),
        })
        if len(refs) >= max_items:
            return refs

    for index, claim in enumerate(criterion_claims, start=1):
        refs.append({
            "ref": f"C{index:03d}",
            "kind": "governed_criterion_claim",
            "evidence": _safe(claim),
        })
        if len(refs) >= max_items:
            return refs

    for index, item in enumerate(source_evidence, start=1):
        refs.append({
            "ref": f"S{index:03d}",
            "kind": str(item.get("evidence_kind") or "source_native_evidence"),
            "evidence": _safe(item),
        })
        if len(refs) >= max_items:
            return refs
    return refs


def _response_schema(policy: SynthesisPolicy) -> dict[str, Any]:
    levels = [level.id for level in policy.semantic_levels]
    return {
        "type": "object",
        "properties": {
            "proposed_overall_level": {
                "type": "string",
                "enum": levels + ["unassessed"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "source_interpretations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evidence_ref": {"type": "string"},
                        "semantic_level": {"type": "string", "enum": levels},
                        "rationale": {"type": "string"},
                    },
                    "required": ["evidence_ref", "semantic_level", "rationale"],
                    "additionalProperties": False,
                },
            },
            "supporting_evidence_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "policy_rules_applied": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainty": {"type": "string"},
        },
        "required": [
            "proposed_overall_level",
            "confidence",
            "rationale",
            "source_interpretations",
            "supporting_evidence_refs",
            "policy_rules_applied",
            "uncertainty",
        ],
        "additionalProperties": False,
    }


def _prompt(
    *,
    format_context: dict[str, Any],
    policy: SynthesisPolicy,
    deterministic_synthesis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> str:
    context = {
        "format": _safe(format_context),
        "policy": _safe(policy.raw),
        "deterministic_config_synthesis": _safe(deterministic_synthesis),
        "evidence": evidence,
        "instructions": {
            "configured_mappings_are_binding": True,
            "interpret_only_explicit_unmapped_source_risk": True,
            "source_interpretations_must_reference_source_native_risk_assessment": True,
            "supporting_evidence_cannot_fabricate_source_rating": True,
            "missing_sources_contribute_nothing": True,
        },
    }
    return (
        "Produce a preservation-risk synthesis using only this bounded context. For source_interpretations, "
        "include only S-prefixed evidence whose kind is source_native_risk_assessment and only when its risk "
        "meaning is explicit enough to map to the configured semantic scale. Do not reinterpret R-prefixed "
        "governed assessments; their configured mapping is binding. Do not reinterpret S-prefixed source-native "
        "risk evidence when the supplied policy already maps that source/value. The application will re-run the "
        "configured scope/aggregation policy after your source interpretations, so your proposed_overall_level is "
        "advisory when mapped source-level assessments exist. When there is no mapped source-level assessment, "
        "you may propose an overall level from cited supporting evidence only if the policy permits. Otherwise "
        "return unassessed.\n\n" + json.dumps(context, indent=2, sort_keys=True, default=str)
    )


def _source_evidence_as_assessment(evidence_item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "source_id": evidence_item.get("source_id"),
            "source_type": evidence_item.get("source_type"),
            "source_record_id": evidence_item.get("source_record_id"),
            "source_label": evidence_item.get("source_name"),
            "native_label": evidence_item.get("native_label"),
            "native_score": evidence_item.get("native_score"),
            "native_scale": evidence_item.get("native_scale"),
            "semantic_level": evidence_item.get("semantic_level"),
            "scope_type": evidence_item.get("scope_type"),
            "scope_name": evidence_item.get("scope_name"),
        }.items()
        if value is not None
    }


def _validate_response(
    response: AIResponse,
    *,
    evidence: list[dict[str, Any]],
    policy: SynthesisPolicy,
) -> dict[str, Any]:
    data = response.structured
    if not isinstance(data, dict):
        raise AIProviderError("AI synthesis did not return a structured JSON object.")

    allowed_levels = {level.id for level in policy.semantic_levels}
    proposed = str(data.get("proposed_overall_level") or "")
    if proposed not in allowed_levels | {"unassessed"}:
        raise AIProviderError(f"AI synthesis returned unsupported overall level '{proposed}'.")
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIProviderError("AI synthesis confidence must be numeric.") from exc
    if not 0 <= confidence <= 1:
        raise AIProviderError("AI synthesis confidence must be between 0 and 1.")

    evidence_by_ref = {str(item["ref"]): item for item in evidence}
    support_refs = [str(ref) for ref in data.get("supporting_evidence_refs") or []]
    unknown_support = sorted(set(support_refs) - set(evidence_by_ref))
    if unknown_support:
        raise AIProviderError(
            "AI synthesis cited evidence refs not supplied by the application: " + ", ".join(unknown_support)
        )
    if proposed != "unassessed" and not support_refs:
        raise AIProviderError("AI synthesis requires supporting evidence refs for an assessed overall level.")

    interpretations: list[dict[str, Any]] = []
    for item in data.get("source_interpretations") or []:
        if not isinstance(item, dict):
            raise AIProviderError("AI source_interpretations entries must be objects.")
        ref = str(item.get("evidence_ref") or "")
        if ref not in evidence_by_ref:
            raise AIProviderError(f"AI source interpretation references unknown evidence ref '{ref}'.")
        referenced = evidence_by_ref[ref]
        if referenced.get("kind") != "source_native_risk_assessment":
            raise AIProviderError(
                f"AI source interpretation ref '{ref}' is not a source_native_risk_assessment."
            )
        source_evidence = referenced.get("evidence")
        if not isinstance(source_evidence, dict):
            raise AIProviderError(f"AI source interpretation ref '{ref}' has invalid evidence payload.")
        configured = normalize_assessment(_source_evidence_as_assessment(source_evidence), policy)
        if configured.get("policy_status") == "mapped":
            raise AIProviderError(
                f"AI source interpretation ref '{ref}' is already normalized by configured rule "
                f"'{configured.get('policy_rule_id')}'. Configured mappings are binding."
            )
        level = str(item.get("semantic_level") or "")
        if level not in allowed_levels:
            raise AIProviderError(f"AI source interpretation uses unsupported level '{level}'.")
        interpretations.append({
            "evidence_ref": ref,
            "semantic_level": level,
            "rationale": str(item.get("rationale") or ""),
        })

    return {
        "proposed_overall_level": proposed,
        "confidence": confidence,
        "rationale": str(data.get("rationale") or ""),
        "source_interpretations": interpretations,
        "supporting_evidence_refs": support_refs,
        "policy_rules_applied": [str(value) for value in data.get("policy_rules_applied") or []],
        "uncertainty": str(data.get("uncertainty") or ""),
        "provider": response.provider,
        "model": response.model,
        "usage": response.to_dict()["usage"],
    }


def synthesize_with_ai(
    provider: AIProvider,
    *,
    format_context: dict[str, Any],
    policy: SynthesisPolicy,
    risk_assessments: list[dict[str, Any]],
    criterion_claims: list[dict[str, Any]],
    source_evidence: list[dict[str, Any]],
    max_evidence_items: int = 80,
) -> dict[str, Any]:
    """Return an AI-assisted but policy-governed overall preservation risk."""
    deterministic = synthesize_assessments(risk_assessments, policy)
    evidence = build_synthesis_evidence(
        risk_assessments=risk_assessments,
        criterion_claims=criterion_claims,
        source_evidence=source_evidence,
        policy=policy,
        max_items=max_evidence_items,
    )
    if not evidence:
        return {
            "status": "skipped_no_evidence",
            "deterministic_synthesis": deterministic,
            "overall_synthesized_risk": deterministic,
        }

    request = AIRequest(
        messages=(
            AIMessage("system", AI_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage(
                "user",
                _prompt(
                    format_context=format_context,
                    policy=policy,
                    deterministic_synthesis=deterministic,
                    evidence=evidence,
                ),
            ),
        ),
        response_schema=_response_schema(policy),
        response_schema_name="preservation_risk_synthesis",
        temperature=0.0,
    )
    response = provider.generate(request)
    ai = _validate_response(response, evidence=evidence, policy=policy)
    evidence_by_ref = {str(item["ref"]): item for item in evidence}

    extra: list[dict[str, Any]] = []
    for interpretation in ai["source_interpretations"]:
        evidence_item = evidence_by_ref[interpretation["evidence_ref"]]["evidence"]
        row = {
            "source_id": evidence_item.get("source_id"),
            "source_type": evidence_item.get("source_type"),
            "source_record_id": evidence_item.get("source_record_id"),
            "source_label": evidence_item.get("source_name"),
            "native_label": evidence_item.get("native_label"),
            "native_score": evidence_item.get("native_score"),
            "native_scale": evidence_item.get("native_scale"),
            "semantic_level": interpretation["semantic_level"],
            "scope_type": evidence_item.get("scope_type") or "contextual",
            "scope_name": evidence_item.get("scope_name"),
            "scope_basis": "ai_interpreted_source_native_risk",
            "policy_status": "ai_interpreted",
            "ai_evidence_ref": interpretation["evidence_ref"],
            "ai_rationale": interpretation["rationale"],
        }
        extra.append({key: value for key, value in row.items() if value is not None})

    policy_result = synthesize_assessments(
        risk_assessments,
        policy,
        extra_normalized_assessments=extra,
    )

    if policy_result.get("assessed"):
        overall = deepcopy(policy_result)
        overall["method"] = "ai_assisted_config_driven_synthesis" if extra else "config_driven_scope_aware_synthesis"
        overall["ai_assisted"] = bool(extra)
        overall["ai_confidence"] = ai["confidence"]
        overall["ai_rationale"] = ai["rationale"]
        overall["ai_uncertainty"] = ai["uncertainty"]
        overall["ai_proposed_overall_level"] = ai["proposed_overall_level"]
        overall["ai_proposal_matches_policy_result"] = (
            ai["proposed_overall_level"] == "unassessed"
            or ai["proposed_overall_level"] == overall.get("semantic_level")
        )
    elif ai["proposed_overall_level"] != "unassessed":
        level = ai["proposed_overall_level"]
        overall = {
            "assessed": True,
            "semantic_level": level,
            "semantic_label": policy.level_by_id[level].label,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "method": "ai_policy_guided_supporting_evidence_synthesis",
            "basis": "no_mapped_source_level_assessment_ai_supporting_evidence",
            "ai_assisted": True,
            "confidence": ai["confidence"],
            "rationale": ai["rationale"],
            "uncertainty": ai["uncertainty"],
            "supporting_evidence_refs": ai["supporting_evidence_refs"],
            "contributors": [deepcopy(evidence_by_ref[ref]) for ref in ai["supporting_evidence_refs"]],
            "contextual_contributors": [],
            "missing_evidence_policy": policy.synthesis["missing_assessment_policy"],
            "numeric_aggregation": policy.synthesis["numeric_aggregation"],
        }
    else:
        overall = deepcopy(policy_result)
        overall["ai_assisted"] = True
        overall["ai_confidence"] = ai["confidence"]
        overall["ai_rationale"] = ai["rationale"]
        overall["ai_uncertainty"] = ai["uncertainty"]

    return {
        "status": "ok",
        "policy": policy.summary(),
        "deterministic_synthesis": deterministic,
        "ai": ai,
        "ai_interpreted_assessments": extra,
        "overall_synthesized_risk": overall,
        "evidence_refs": evidence,
        "authority_boundary": (
            "Configured mappings and synthesis rules are binding. AI may normalize explicit unmapped source-native "
            "risk findings and, only when no mapped source-level assessment exists, synthesize from cited supporting "
            "evidence. Missing evidence contributes nothing and heterogeneous numeric source scales are never averaged."
        ),
    }
