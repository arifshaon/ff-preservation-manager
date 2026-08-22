from __future__ import annotations

import json
import math
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

_USER_INSTRUCTION = (
    "Using the supplied evidence, methodology, deterministic baseline, and any capabilities available to you, return "
    "your synthesized preservation-risk analysis. The deterministic baseline is context, not a required answer: if "
    "you differ, explain why. If you obtain information externally, distinguish it clearly from supplied registry "
    "evidence. Do not invent evidence for missing sources."
)

_EVIDENCE_KEYS = (
    "source_id",
    "source_type",
    "source_record_id",
    "source_label",
    "source_name",
    "native_label",
    "native_score",
    "native_scale",
    "normalized_band",
    "semantic_level",
    "scope_type",
    "scope_name",
    "scope_basis",
    "policy_status",
    "policy_rule_id",
    "criterion_id",
    "evidence_field",
    "native_field",
    "value",
    "normalized_value",
    "answer",
    "source_value",
    "source_url",
    "link_basis",
    "mapping_version",
    "status",
    "confidence",
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


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    """Bound verbose source-native payloads without changing the stored evidence."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 1200 else value[:1200] + "…"
    if depth >= 3:
        return _safe(value, max_string=500)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                result["_truncated_fields"] = len(value) - 24
                break
            result[str(key)] = _compact_value(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        result = [_compact_value(item, depth=depth + 1) for item in values[:24]]
        if len(values) > 24:
            result.append({"_truncated_items": len(values) - 24})
        return result
    return _compact_value(str(value), depth=depth + 1)


def _compact_evidence_ref(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    compact = {
        key: _compact_value(evidence.get(key))
        for key in _EVIDENCE_KEYS
        if evidence.get(key) is not None
    }
    # Preserve a small amount of unclassified evidence when a future source has
    # not yet adopted the common fields above.
    if not compact and evidence:
        compact = _compact_value(evidence)
    return {
        "ref": str(item.get("ref") or ""),
        "kind": str(item.get("kind") or "source_evidence"),
        "evidence": compact,
    }


def _evidence_priority(item: dict[str, Any]) -> int:
    kind = str(item.get("kind") or "")
    if kind in {"governed_source_risk_assessment", "config_normalized_source_risk_assessment"}:
        return 0
    if kind == "governed_criterion_claim":
        return 1
    if kind == "source_native_risk_assessment":
        return 2
    if kind in {"source_native_sustainability_factor", "source_native_documentation"}:
        return 3
    return 4


def _framework_summary(framework: Any | None, *, minimal: bool = False) -> dict[str, Any] | None:
    if framework is None:
        return None
    questions = []
    for question in getattr(framework, "questions", ()):
        row = {
            "question_id": getattr(question, "id", None),
            "label": getattr(question, "label", None),
            "domain_id": getattr(question, "domain_id", None),
        }
        if not minimal:
            row.update({
                "critical": bool(getattr(question, "critical", False)),
                "evidence_fields": list(getattr(question, "evidence_fields", ()) or ()),
                "applicability": list(getattr(question, "applicability", ()) or ()),
            })
        questions.append(row)
    return {
        "framework_id": getattr(framework, "framework_id", None),
        "version": getattr(framework, "version", None),
        "calibration_status": getattr(framework, "calibration_status", None),
        "questions": questions,
    }


def _policy_summary(policy: SynthesisPolicy) -> dict[str, Any]:
    raw = policy.raw if isinstance(policy.raw, dict) else {}
    return {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "semantic_levels": _safe(raw.get("semantic_levels") or []),
        "source_rules": [
            {
                key: _safe(item.get(key))
                for key in ("rule_id", "source_match", "role", "value_fields", "value_map", "default_scope")
                if item.get(key) is not None
            }
            for item in raw.get("source_rules") or []
            if isinstance(item, dict)
        ],
        "synthesis": _safe(policy.synthesis),
        "evidence_source_roles": _safe(raw.get("evidence_source_roles") or []),
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


def _provider_config(provider: AIProvider) -> Any | None:
    config = getattr(provider, "config", None)
    if config is not None:
        return config
    delegate = getattr(provider, "delegate", None)
    return getattr(delegate, "config", None)


def _estimate_tokens(text: str) -> int:
    """Conservative provider-neutral estimate used only for preflight budgeting."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.0))


def _token_budget(provider: AIProvider) -> dict[str, Any]:
    config = _provider_config(provider)
    configured_tpm = getattr(config, "tokens_per_minute", None) if config is not None else None
    configured_output = getattr(config, "max_output_tokens", None) if config is not None else None
    if configured_tpm is None:
        return {
            "configured_tokens_per_minute": None,
            "configured_max_output_tokens": configured_output,
            "effective_max_output_tokens": configured_output,
            "safety_reserve_tokens": None,
            "prompt_budget_tokens": None,
            "estimation_method": "conservative_character_estimate_3_chars_per_token",
        }

    tpm = int(configured_tpm)
    requested_output = int(configured_output or 1200)
    # Do not allow one response reservation to consume an excessive portion of
    # a low-TPM deployment. This affects only the AI response allowance; it does
    # not change source data or deterministic assessment behavior.
    effective_output = min(requested_output, max(256, int(tpm * 0.20)))
    safety = max(500, int(tpm * 0.15))
    prompt_budget = tpm - effective_output - safety
    if prompt_budget < 800:
        raise AIProviderError(
            "Configured tokens_per_minute is too small for capability-driven synthesis after reserving output and "
            "rate-limit safety headroom. Increase tokens_per_minute or reduce max_output_tokens."
        )
    return {
        "configured_tokens_per_minute": tpm,
        "configured_max_output_tokens": configured_output,
        "effective_max_output_tokens": effective_output,
        "safety_reserve_tokens": safety,
        "prompt_budget_tokens": prompt_budget,
        "estimation_method": "conservative_character_estimate_3_chars_per_token",
    }


def _build_context(
    *,
    format_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    governed_synthesis: dict[str, Any],
    policy: SynthesisPolicy,
    framework: Any | None,
    capabilities_available: dict[str, Any],
    minimal_framework: bool,
) -> dict[str, Any]:
    return {
        "format": _safe(format_context, max_string=1200),
        "registry_database_evidence": evidence,
        "governed_config_synthesis": _safe(governed_synthesis, max_string=1200),
        "synthesis_policy": _policy_summary(policy),
        "assessment_framework": _framework_summary(framework, minimal=minimal_framework),
        "capabilities_available": _safe(capabilities_available),
    }


def _request_estimate(context: dict[str, Any], schema: dict[str, Any]) -> tuple[str, int]:
    context_json = json.dumps(context, separators=(",", ":"), sort_keys=True, default=str)
    user_text = _USER_INSTRUCTION + "\n\n" + context_json
    estimated = _estimate_tokens(
        AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT
        + user_text
        + json.dumps(schema, separators=(",", ":"), sort_keys=True, default=str)
    ) + 120
    return user_text, estimated


def _fit_context_to_budget(
    *,
    format_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    governed_synthesis: dict[str, Any],
    policy: SynthesisPolicy,
    framework: Any | None,
    capabilities_available: dict[str, Any],
    schema: dict[str, Any],
    prompt_budget_tokens: int | None,
) -> tuple[list[dict[str, Any]], str, int, bool, list[str]]:
    supplied = list(evidence)
    minimal_framework = False
    omitted_refs: list[str] = []

    def build() -> tuple[str, int]:
        context = _build_context(
            format_context=format_context,
            evidence=supplied,
            governed_synthesis=governed_synthesis,
            policy=policy,
            framework=framework,
            capabilities_available=capabilities_available,
            minimal_framework=minimal_framework,
        )
        return _request_estimate(context, schema)

    user_text, estimated = build()
    if prompt_budget_tokens is None or estimated <= prompt_budget_tokens:
        return supplied, user_text, estimated, minimal_framework, omitted_refs

    # Remove lower-priority evidence first. Governed source-level risk assessments
    # are retained unless the fixed prompt itself cannot fit the configured TPM.
    while estimated > prompt_budget_tokens:
        removable_indexes = [
            index for index, item in enumerate(supplied)
            if _evidence_priority(item) > 0
        ]
        if not removable_indexes:
            break
        worst_priority = max(_evidence_priority(supplied[index]) for index in removable_indexes)
        remove_index = max(
            index for index in removable_indexes
            if _evidence_priority(supplied[index]) == worst_priority
        )
        removed = supplied.pop(remove_index)
        if removed.get("ref"):
            omitted_refs.append(str(removed["ref"]))
        user_text, estimated = build()

    if estimated > prompt_budget_tokens and framework is not None:
        minimal_framework = True
        user_text, estimated = build()

    if estimated > prompt_budget_tokens:
        raise AIProviderError(
            "The mandatory synthesis context exceeds the prompt budget derived from tokens_per_minute even after "
            "compacting optional evidence. Increase tokens_per_minute or reduce max_output_tokens."
        )
    return supplied, user_text, estimated, minimal_framework, omitted_refs


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


def _generate_capability_response(provider: AIProvider, request: AIRequest) -> AIResponse:
    """Use the provider's single-call capability path without bypassing wrappers."""
    direct = getattr(provider, "generate_with_capabilities", None)
    if callable(direct):
        return direct(request)

    delegate = getattr(provider, "delegate", None)
    delegated = getattr(delegate, "generate_with_capabilities", None)
    guard = getattr(provider, "_call_with_rate_limit_guard", None)
    if callable(delegated) and callable(guard):
        return guard(delegated, request)
    if callable(delegated):
        return delegated(request)
    return provider.generate(request)


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
    """Ask the AI client once, fitting context to an optional TPM budget."""
    total_possible = max(1, len(risk_assessments) + len(criterion_claims) + len(source_evidence))
    all_evidence = build_synthesis_evidence(
        risk_assessments=[dict(item) for item in risk_assessments if isinstance(item, dict)],
        criterion_claims=[dict(item) for item in criterion_claims if isinstance(item, dict)],
        source_evidence=[dict(item) for item in source_evidence if isinstance(item, dict)],
        policy=policy,
        max_items=total_possible,
    )
    compacted = [_compact_evidence_ref(item) for item in all_evidence]
    ranked = sorted(enumerate(compacted), key=lambda pair: (_evidence_priority(pair[1]), pair[0]))
    candidate_evidence = [item for _, item in ranked[:max(1, int(max_evidence_items))]]

    capabilities_available = provider.describe().get("capabilities") or {}
    budget = _token_budget(provider)
    schema = _response_schema(policy)
    database_evidence, user_text, estimated_prompt_tokens, minimal_framework, omitted_for_budget = _fit_context_to_budget(
        format_context=format_context,
        evidence=candidate_evidence,
        governed_synthesis=governed_synthesis,
        policy=policy,
        framework=framework,
        capabilities_available=capabilities_available,
        schema=schema,
        prompt_budget_tokens=budget.get("prompt_budget_tokens"),
    )

    omitted_by_item_limit = [
        str(item.get("ref")) for _, item in ranked[max(1, int(max_evidence_items)):]
        if item.get("ref")
    ]
    omitted_refs = omitted_by_item_limit + omitted_for_budget
    budget.update({
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "evidence_items_available": len(compacted),
        "evidence_items_supplied": len(database_evidence),
        "evidence_items_omitted": len(omitted_refs),
        "omitted_evidence_refs": omitted_refs,
        "framework_compacted": minimal_framework,
        "context_trimmed_for_token_budget": bool(omitted_for_budget or minimal_framework),
    })

    request = AIRequest(
        messages=(
            AIMessage("system", AI_CAPABILITY_SYNTHESIS_SYSTEM_PROMPT),
            AIMessage("user", user_text),
        ),
        response_schema=schema,
        response_schema_name="preservation_risk_ai_synthesis",
        temperature=0.0,
        max_output_tokens=budget.get("effective_max_output_tokens"),
    )

    response = _generate_capability_response(provider, request)
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
    overall["token_budget"] = dict(budget)

    return {
        "status": "ok",
        "mode": "capability_driven_ai_synthesis",
        "governed_synthesis": governed_synthesis,
        "overall_synthesized_risk": overall,
        "database_evidence_refs": database_evidence,
        "token_budget": budget,
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
