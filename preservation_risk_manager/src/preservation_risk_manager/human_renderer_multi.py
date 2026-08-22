from __future__ import annotations

from typing import Any

from preservation_risk_manager import human_renderer as base


def _display(value: Any, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _source_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("source_id") or ""),
        str(item.get("source_record_id") or ""),
        str(item.get("scope_type") or ""),
    )


def _overall_source_risk(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("overall_synthesized_risk")
    if isinstance(direct, dict):
        return direct
    context = payload.get("external_risk_context") or {}
    if not isinstance(context, dict):
        return {}
    policy = context.get("policy_synthesized_risk")
    if isinstance(policy, dict):
        return policy
    registry = context.get("registry_synthesized_risk")
    return registry if isinstance(registry, dict) else {}


def _render_source_assessment(item: dict[str, Any], *, role: str | None = None) -> list[str]:
    source = _display(item.get("source_label") or item.get("source_id") or item.get("source_type"), "Source")
    native = item.get("native_label")
    native_score = item.get("native_score")
    native_scale = item.get("native_scale")
    semantic = item.get("semantic_label") or item.get("semantic_level") or item.get("normalized_band")
    scope = item.get("scope_type")
    scope_name = item.get("scope_name")

    lines = [source]
    if native is not None:
        native_text = str(native)
        if native_score is not None:
            native_text += f" (native score {native_score}"
            if native_scale:
                native_text += f", {native_scale}"
            native_text += ")"
        elif native_scale:
            native_text += f" ({native_scale})"
        lines.append(f"  Native assessment: {native_text}")
    elif native_score is not None:
        lines.append(
            f"  Native assessment: {native_score}"
            + (f" ({native_scale})" if native_scale else "")
        )
    if semantic is not None:
        lines.append(f"  Mapped semantic risk: {semantic}")
    if scope:
        scope_text = str(scope).replace("_", " ")
        if scope_name:
            scope_text += f" — {scope_name}"
        lines.append(f"  Scope: {scope_text}")
    if role:
        lines.append(f"  Synthesis role: {role}")
    return lines


def _render_ai_synthesis_disclosure(response: dict[str, Any]) -> list[str]:
    synthesis = response.get("ai_synthesis")
    if not isinstance(synthesis, dict):
        return []

    status = str(synthesis.get("status") or "unknown")
    lines = ["AI-assisted synthesis", f"- Status: {status}."]
    provider = synthesis.get("provider") or (synthesis.get("ai") or {}).get("provider")
    if provider:
        if isinstance(provider, dict):
            provider_name = provider.get("provider") or provider.get("model") or provider
        else:
            provider_name = provider
        lines.append(f"- Provider: {provider_name}.")

    overall = synthesis.get("overall_synthesized_risk") or {}
    if status == "ok":
        if overall.get("semantic_level"):
            lines.append(f"- AI-assisted synthesized level: {overall.get('semantic_level')}.")
        relation = overall.get("governed_baseline_relation")
        if relation:
            lines.append(f"- Relation to governed config baseline: {str(relation).replace('_', ' ')}.")
        try:
            lines.append(f"- Confidence: {float(overall.get('confidence')):.2f}.")
        except (TypeError, ValueError):
            pass

        available = overall.get("capabilities_available") or {}
        used = overall.get("capabilities_used") or {}
        if isinstance(available, dict) and available.get("web_search"):
            lines.append(
                "- Web search capability was available to the AI client; "
                + ("the model used it." if used.get("web_search") else "the model did not use it.")
            )

        external = synthesis.get("external_capability") or {}
        if isinstance(external, dict) and external.get("error"):
            lines.append(f"- External capability note: {external.get('error')}")
        sources = [item for item in (external.get("sources") if isinstance(external, dict) else []) or [] if isinstance(item, dict)]
        if sources:
            lines.append("- External sources returned:")
            for item in sources[:10]:
                title = item.get("title") or item.get("url")
                lines.append(f"  - {item.get('ref')}: {title} — {item.get('url')}")

        considerations = [item for item in overall.get("considerations") or [] if isinstance(item, dict)]
        if considerations:
            lines.append("- Material AI considerations:")
            for item in considerations[:8]:
                basis = str(item.get("basis") or "model_reasoning").replace("_", " ")
                effect = str(item.get("risk_effect") or "uncertain").replace("_", " ")
                lines.append(f"  - {item.get('finding')} [{basis}; {effect}]")

        warnings = [str(item) for item in overall.get("quality_warnings") or []]
        for warning in warnings:
            lines.append(f"- Quality warning: {warning}")
    elif status == "error_config_synthesis_retained":
        lines.append("- AI synthesis failed; the deterministic/config synthesis was retained unchanged.")
        if synthesis.get("error"):
            lines.append(f"- Error: {synthesis.get('error')}")
        if overall.get("semantic_level"):
            lines.append(f"- Retained overall level: {overall.get('semantic_level')}.")

    boundary = synthesis.get("authority_boundary")
    if boundary:
        lines.append(f"- Boundary: {boundary}")
    return lines


def _append_ai_disclosure(rendered: str, response: dict[str, Any]) -> str:
    sections: list[str] = []
    identification = base._render_identification_disclosure(response)
    if identification:
        sections.append("\n".join(identification))

    synthesis = _render_ai_synthesis_disclosure(response)
    if synthesis:
        sections.append("\n".join(synthesis))

    ai_risk = response.get("ai_risk_assessment")
    synthesis_only = (
        isinstance(ai_risk, dict)
        and ai_risk.get("ai_mode") == "synthesize"
        and ai_risk.get("status") in {"not_requested_synthesis_only", "synthesis_only"}
    )
    if not synthesis_only:
        risk = base._render_ai_risk_disclosure(response)
        if risk:
            sections.append("\n".join(risk))

    if not sections:
        return rendered
    return rendered + "\n\n" + "\n\n".join(sections)


def _render_synthesized_single_assessment(response: dict[str, Any]) -> str | None:
    payload = response.get("result") or {}
    if not isinstance(payload, dict):
        return None
    context = payload.get("external_risk_context") or {}
    if not isinstance(context, dict):
        return None
    assessments = [item for item in context.get("assessments") or [] if isinstance(item, dict)]
    overall = _overall_source_risk(payload)
    if not assessments and not overall.get("assessed"):
        return None

    fmt = payload.get("format") or {}
    label = _display(fmt.get("label") or response.get("matched_label") or fmt.get("format_id"), "Format")
    puids = fmt.get("puids") or []
    puid = response.get("matched_puid") or (puids[0] if puids else None)
    heading = label + (f" — {puid}" if puid and str(puid) not in label else "")
    lines = [heading, ""]

    ai_capability = str(overall.get("method") or "") == "ai_capability_driven_synthesis"
    governed_baseline = overall.get("governed_baseline") if isinstance(overall.get("governed_baseline"), dict) else {}

    if overall.get("assessed") and overall.get("semantic_level"):
        overall_label = overall.get("semantic_label") or str(overall.get("semantic_level")).replace("_", " ").title()
        lines.extend([
            "Overall synthesized preservation risk",
            f"{overall_label}",
        ])
        method = overall.get("method")
        if method:
            lines.append(f"Method: {str(method).replace('_', ' ')}")
        policy_id = overall.get("policy_id") or (context.get("synthesis_policy") or {}).get("policy_id")
        policy_version = overall.get("policy_version") or (context.get("synthesis_policy") or {}).get("version")
        if policy_id:
            lines.append(f"Policy context: {policy_id}" + (f" v{policy_version}" if policy_version else ""))
        if ai_capability:
            baseline_label = governed_baseline.get("semantic_label") or governed_baseline.get("semantic_level")
            if baseline_label:
                lines.append(f"Governed config baseline: {baseline_label}")
            capabilities = overall.get("capabilities_available") or {}
            used = overall.get("capabilities_used") or {}
            if isinstance(capabilities, dict) and capabilities.get("web_search"):
                lines.append(
                    "AI web-search capability: available; "
                    + ("used by the model." if used.get("web_search") else "not used by the model.")
                )
            else:
                lines.append("AI web-search capability: not available from this provider/client.")
        elif overall.get("ai_assisted"):
            lines.append("AI assistance: yes.")
    else:
        lines.extend([
            "Overall synthesized preservation risk",
            "Not assessed — the available evidence did not support a synthesized risk level.",
        ])

    role_basis = governed_baseline if ai_capability and governed_baseline else overall
    primary_keys = {
        _source_key(item)
        for item in role_basis.get("contributors") or []
        if isinstance(item, dict)
    }
    contextual_keys = {
        _source_key(item)
        for item in role_basis.get("contextual_contributors") or []
        if isinstance(item, dict)
    }

    if assessments:
        lines.extend(["", "Source assessments"])
        for item in assessments:
            key = _source_key(item)
            role = None
            if key in primary_keys:
                role = "governed baseline headline contributor" if ai_capability else "headline contributor"
            elif key in contextual_keys:
                role = "governed baseline broader-scope context" if ai_capability else "broader-scope context"
            lines.extend(_render_source_assessment(item, role=role))

    if overall.get("assessed"):
        lines.extend(["", "How the overall risk was determined"])
        if ai_capability:
            lines.append(
                "The AI received the collected registry evidence, the deterministic/config baseline, the synthesis "
                "configuration, and the assessment framework as context. Any provider capabilities available to the "
                "AI client were made available; the model decided whether to use them."
            )
            relation = overall.get("governed_baseline_relation")
            if relation:
                lines.append(f"The AI result is {str(relation).replace('_', ' ')} relative to the governed baseline.")
            considerations = [item for item in overall.get("considerations") or [] if isinstance(item, dict)]
            for item in considerations[:8]:
                lines.append(
                    f"- {item.get('finding')} — {str(item.get('basis') or 'model_reasoning').replace('_', ' ')}; "
                    f"{str(item.get('risk_effect') or 'uncertain').replace('_', ' ')}."
                )
            lines.append(
                "The AI-assisted result does not rewrite the source records or the governed baseline; both remain "
                "available for the consumer to evaluate."
            )
        else:
            selected_scopes = overall.get("selected_scope_types") or []
            if selected_scopes:
                lines.append(
                    "The configured policy selected the most-specific populated scope: "
                    + ", ".join(str(scope).replace("_", " ") for scope in selected_scopes)
                    + "."
                )
            levels = overall.get("contributing_levels") or []
            if len(levels) > 1:
                lines.append(
                    "Multiple assessments existed at that same scope; the configured conservative rule selected "
                    "the highest semantic concern at that scope."
                )
            elif levels:
                lines.append(
                    f"The applicable headline assessment at that scope mapped to {str(levels[0]).replace('_', ' ')} concern."
                )
            if overall.get("contextual_contributors"):
                lines.append(
                    "Broader-scope assessments are retained as context and do not override the more-specific headline assessment."
                )
            lines.append("Missing sources contribute nothing, and heterogeneous native source scales are not numerically averaged.")

    rationale = overall.get("rationale") or overall.get("ai_rationale")
    uncertainty = overall.get("uncertainty") or overall.get("ai_uncertainty")
    if rationale:
        lines.extend(["", "AI synthesis rationale" if ai_capability else "Synthesis rationale", str(rationale)])
    if uncertainty:
        lines.append(f"Uncertainty: {uncertainty}")

    warnings = [str(item) for item in overall.get("quality_warnings") or []]
    if warnings:
        lines.extend(["", "AI quality notes"])
        for warning in warnings:
            lines.append(f"- {warning}")

    parity = context.get("registry_synthesis_parity") or {}
    if isinstance(parity, dict) and parity.get("registry_level") is not None:
        if parity.get("semantic_level_match"):
            prefix = "governed config baseline" if ai_capability else "policy-derived semantic level"
            lines.append(f"Config migration check: the {prefix} matches the existing locked MongoDB synthesis.")
        else:
            lines.append(
                "Config migration warning: the governed policy-derived semantic level differs from the existing locked MongoDB synthesis; review before operational use."
            )

    return "\n".join(lines)


def _render_multi_puid(response: dict[str, Any]) -> str:
    assessments = [item for item in response.get("assessments") or [] if isinstance(item, dict)]
    matched_count = int(response.get("matched_puid_count") or len(assessments))
    assessed_count = int(response.get("assessed_puid_count") or len(assessments))

    if matched_count != assessed_count:
        title = f"Preservation-risk assessments for {assessed_count} of {matched_count} matched PRONOM PUIDs"
    else:
        title = f"Preservation-risk assessments for {assessed_count} matched PRONOM PUIDs"

    lines = [title, ""]

    if response.get("human_format_assessment_limit_applied"):
        limit = int(response.get("human_format_assessment_limit") or 0)
        unassessed = int(response.get("unassessed_puid_count") or 0)
        lines.extend([
            f"{matched_count} matching formats were found. The configured human assessment limit is {limit}, "
            f"so only the first {assessed_count} PUIDs were assessed. The remaining {unassessed} PUIDs were not assessed.",
            "",
        ])

    lines.append("Each assessed PUID was evaluated independently; no family-level risk score was invented.")

    for index, assessment in enumerate(assessments, start=1):
        puid = _display(assessment.get("matched_puid"), "PUID unknown")
        label = _display(assessment.get("matched_label"), puid)
        version = assessment.get("matched_version")
        heading = f"{index}. {label} ({puid})"
        if version not in (None, "") and str(version) not in label:
            heading += f" — version {version}"
        lines.extend(["", heading])

        rendered = _render_synthesized_single_assessment(assessment) or base.render_human_response(assessment)
        for line in rendered.splitlines():
            lines.append(f"   {line}" if line else "")

    return _append_ai_disclosure("\n".join(lines), response)


def render_human_response(response: dict[str, Any]) -> str:
    """Render source-synthesized human risk results and multi-PUID fan-out."""
    if response.get("human_multi_puid_assessment"):
        return _render_multi_puid(response)
    action = str((response.get("request") or {}).get("action") or "")
    if action == "assess_format":
        rendered = _render_synthesized_single_assessment(response)
        if rendered is not None:
            return _append_ai_disclosure(rendered, response)
    return base.render_human_response(response)
