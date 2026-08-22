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
            lines.append(
                f"Policy: {policy_id}" + (f" v{policy_version}" if policy_version else "")
            )
        if overall.get("ai_assisted"):
            lines.append("AI assistance: yes — bounded by the configured synthesis policy and supplied evidence.")
    else:
        lines.extend([
            "Overall synthesized preservation risk",
            "Not assessed — no source assessment could be mapped or supported sufficiently for synthesis.",
        ])

    primary_keys = {
        _source_key(item)
        for item in overall.get("contributors") or []
        if isinstance(item, dict)
    }
    contextual_keys = {
        _source_key(item)
        for item in overall.get("contextual_contributors") or []
        if isinstance(item, dict)
    }

    if assessments:
        lines.extend(["", "Source assessments"])
        for item in assessments:
            key = _source_key(item)
            role = None
            if key in primary_keys:
                role = "headline contributor"
            elif key in contextual_keys:
                role = "broader-scope context"
            lines.extend(_render_source_assessment(item, role=role))

    if overall.get("assessed"):
        lines.extend(["", "How the overall risk was determined"])
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

    rationale = overall.get("ai_rationale") or overall.get("rationale")
    uncertainty = overall.get("ai_uncertainty") or overall.get("uncertainty")
    if rationale:
        lines.extend(["", "AI synthesis rationale", str(rationale)])
    if uncertainty:
        lines.append(f"Uncertainty: {uncertainty}")

    parity = context.get("registry_synthesis_parity") or {}
    if isinstance(parity, dict) and parity.get("registry_level") is not None:
        if parity.get("semantic_level_match"):
            lines.append(
                "Config migration check: the policy-derived semantic level matches the existing locked MongoDB synthesis."
            )
        else:
            lines.append(
                "Config migration warning: the policy-derived semantic level differs from the existing locked MongoDB synthesis; review before operational use."
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

    return base._append_ai_disclosure("\n".join(lines), response)


def render_human_response(response: dict[str, Any]) -> str:
    """Render source-synthesized human risk results and multi-PUID fan-out."""
    if response.get("human_multi_puid_assessment"):
        return _render_multi_puid(response)
    action = str((response.get("request") or {}).get("action") or "")
    if action == "assess_format":
        rendered = _render_synthesized_single_assessment(response)
        if rendered is not None:
            return base._append_ai_disclosure(rendered, response)
    return base.render_human_response(response)
