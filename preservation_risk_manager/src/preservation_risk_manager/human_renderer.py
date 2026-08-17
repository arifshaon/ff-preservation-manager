from __future__ import annotations

from collections import defaultdict
from typing import Any


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "unknown"


def _display(value: Any, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _format_name(result: dict[str, Any]) -> str:
    fmt = result.get("format") or {}
    return _display(fmt.get("label") or fmt.get("format_id"), "Format")


def _evidence_lines(evidence: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in evidence:
        source = item.get("source_id") or item.get("source_type") or "registry evidence"
        record = item.get("source_record_id")
        criterion = item.get("criterion_id")
        value = item.get("value")
        parts = [str(source)]
        if record:
            parts.append(str(record))
        if criterion:
            parts.append(str(criterion))
        if value is not None:
            parts.append(f"value={value}")
        lines.append(" / ".join(parts))
    return lines


def _render_question_assessment(payload: dict[str, Any]) -> str:
    name = _format_name(payload)
    questions = payload.get("questions") or []
    answered = int(payload.get("answered_question_count") or 0)
    selected = int(payload.get("selected_question_count") or len(questions))
    coverage = _pct(payload.get("evidence_completeness"))
    overall = payload.get("overall_framework_assessment") or {}

    lines = [f"{name} preservation-risk assessment", ""]
    lines.append(f"Evidence coverage: {answered} of {selected} selected questions answered ({coverage}).")

    if not overall.get("banding_enabled", True):
        lines.append(
            "Overall Low/Moderate/High banding is not reported because this framework is marked "
            f"{_display(overall.get('calibration_status'), 'uncalibrated')} and banding is disabled."
        )
    elif overall.get("risk_band"):
        lines.append(
            f"Overall framework result: {_display(overall.get('risk_band'))} "
            f"(score {_display(overall.get('score'))}/{_display(overall.get('max_score'))})."
        )
    elif overall.get("band_suppressed_reason"):
        lines.append(
            "No overall risk band can be assigned: "
            f"{str(overall.get('band_suppressed_reason')).replace('_', ' ')}."
        )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        grouped[(
            _display(question.get("domain_id"), "other"),
            _display(question.get("domain_label"), "Assessment"),
        )].append(question)

    for (_, domain_label), rows in grouped.items():
        lines.extend(["", domain_label])
        for row in rows:
            label = _display(row.get("label"), _display(row.get("question_id")))
            answer_label = row.get("answer_label")
            answer_id = row.get("answer_id")
            status = _display(row.get("derivation_status"), "unknown")
            abstention = bool(row.get("abstention"))

            if abstention or answer_id == "unknown" or not answer_label:
                conclusion = "Unknown / insufficient evidence"
            else:
                conclusion = str(answer_label)

            lines.append(f"- {label}")
            lines.append(f"  Assessment: {conclusion}.")
            lines.append(f"  Derivation: {status.replace('_', ' ')}.")

            evidence = [item for item in row.get("evidence") or [] if isinstance(item, dict)]
            if evidence:
                lines.append(f"  Supporting evidence ({len(evidence)}):")
                for evidence_line in _evidence_lines(evidence):
                    lines.append(f"    - {evidence_line}")
            else:
                fields = row.get("evidence_fields") or []
                if fields:
                    lines.append(
                        "  Evidence gap: no usable registry claim currently answers "
                        + ", ".join(str(field) for field in fields)
                        + "."
                    )
                else:
                    lines.append("  Evidence gap: no usable supporting evidence is currently available.")

            guidance = row.get("guidance")
            if guidance:
                lines.append(f"  Assessment guidance: {guidance}")

    if selected and answered < selected:
        lines.extend([
            "",
            "Interpretation",
            f"This is a partial assessment. {selected - answered} selected question(s) remain unresolved, so the absence of a positive risk finding must not be interpreted as evidence that no risk exists.",
        ])
    return "\n".join(lines)


def _render_single_assessment(payload: dict[str, Any]) -> str:
    name = _format_name(payload)
    band = payload.get("risk_band")
    status = _display(payload.get("analysis_status"))
    completeness = _pct(payload.get("evidence_completeness"))
    lines = [f"{name} preservation-risk assessment", ""]

    if band:
        lines.append(
            f"Current deterministic risk band: {band}. Score: {_display(payload.get('score'))}/{_display(payload.get('max_score'))}."
        )
    elif not payload.get("banding_enabled", True):
        lines.append(
            "No overall Low/Moderate/High band is reported because the active framework is not calibrated for banding."
        )
    else:
        reason = str(payload.get("band_suppressed_reason") or "insufficient evidence").replace("_", " ")
        lines.append(f"No risk band can currently be assigned because of {reason}.")

    lines.append(f"Assessment status: {status}. Evidence completeness: {completeness}.")
    factors = payload.get("main_risk_factors") or []
    if factors:
        lines.extend(["", "Risk factors identified:"])
        for factor in factors:
            lines.append(
                f"- {_display(factor.get('question_id'))}: {_display(factor.get('answer_id'))} "
                f"(weighted points {_display(factor.get('weighted_points'))})."
            )
    else:
        lines.extend(["", "No positive risk factor was identified among the questions that were successfully answered."])

    missing = int(payload.get("missing_count") or 0)
    abstentions = int(payload.get("abstention_count") or 0)
    if missing or abstentions:
        lines.append(
            f"Caution: {missing} question(s) are missing evidence and {abstentions} question(s) are unresolved/abstained."
        )
    return "\n".join(lines)


def _render_question_catalog(response: dict[str, Any]) -> str:
    rows = response.get("results") or []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_display(row.get("domain_label"), "Other")].append(row)
    lines = [f"Preservation-risk assessment questions ({len(rows)})"]
    for domain, questions in grouped.items():
        lines.extend(["", domain])
        for row in questions:
            applicability = row.get("applicability") or []
            suffix = f" [applies to: {', '.join(applicability)}]" if applicability else ""
            lines.append(f"- {_display(row.get('label'))}{suffix}")
    return "\n".join(lines)


def _render_at_risk(response: dict[str, Any]) -> str:
    results = response.get("results") or []
    summary = response.get("assessment_summary") or {}
    filters = response.get("filters") or {}
    family = filters.get("family")
    title = f"At-risk {family} formats" if family else "At-risk formats"
    lines = [title, ""]
    band_counts = summary.get("band_counts") or {}
    lines.append(
        "Assessment coverage: "
        f"High {band_counts.get('High', 0)}, Moderate {band_counts.get('Moderate', 0)}, "
        f"Low {band_counts.get('Low', 0)}, Unbanded {band_counts.get('Unbanded', 0)}."
    )
    if results:
        lines.extend(["", "Formats requiring attention:"])
        for row in results:
            fmt = row.get("format") or {}
            lines.append(
                f"- {_display(fmt.get('label') or fmt.get('format_id'))}: {_display(row.get('risk_band'))} "
                f"(score {_display(row.get('score'))}/{_display(row.get('max_score'))}, evidence {_pct(row.get('evidence_completeness'))})."
            )
    else:
        lines.extend(["", "No format with an assigned Moderate or High band was found in the requested set."])
    if response.get("coverage_warning"):
        lines.extend(["", "Coverage warning", str(response["coverage_warning"])])
    return "\n".join(lines)


def _render_evidence_gaps(response: dict[str, Any]) -> str:
    results = response.get("results") or []
    summary = response.get("gap_summary") or {}
    lines = ["Evidence-gap assessment", ""]
    lines.append(
        f"{summary.get('formats_with_gaps', len(results))} format(s) have unresolved evidence gaps; "
        f"{summary.get('fully_covered_formats', 0)} are fully covered for the active framework."
    )
    for row in results:
        fmt = row.get("format") or {}
        lines.extend(["", f"{_display(fmt.get('label') or fmt.get('format_id'))}: {_display(row.get('gap_classification'))}"])
        for gap in row.get("missing_questions") or []:
            lines.append(
                f"- {_display(gap.get('label'), _display(gap.get('question_id')))}: "
                f"{str(gap.get('gap_reason') or 'unresolved').replace('_', ' ')}."
            )
    return "\n".join(lines)


def _render_remediation(response: dict[str, Any]) -> str:
    results = response.get("results") or []
    summary = response.get("remediation_summary") or {}
    lines = ["Evidence-remediation priorities", ""]
    lines.append(
        f"{summary.get('formats_requiring_remediation', len(results))} format(s) require remediation; "
        f"{summary.get('remediation_item_count', 0)} action item(s) identified."
    )
    for row in results:
        fmt = row.get("format") or {}
        lines.extend(["", _display(fmt.get("label") or fmt.get("format_id"))])
        for item in row.get("remediation_items") or []:
            lines.append(
                f"- {_display(item.get('priority'))} — {_display(item.get('action_type')).replace('_', ' ')}"
                + (f" for {_display(item.get('question_label'), _display(item.get('question_id')))}" if item.get("question_id") else "")
                + "."
            )
            values = item.get("observed_values") or []
            if values:
                lines.append(f"  Observed unmapped value(s): {', '.join(str(value) for value in values)}.")
    return "\n".join(lines)


def _render_search(response: dict[str, Any]) -> str:
    results = response.get("results") or []
    lines = [f"Found {len(results)} matching format(s)."]
    for row in results:
        lines.append(f"- {_display(row.get('label') or row.get('format_id'))} ({_display(row.get('format_id'))})")
    return "\n".join(lines)


def render_human_response(response: dict[str, Any]) -> str:
    """Render canonical request JSON as an archivist-facing detailed answer.

    The renderer does not add preservation facts. It only explains data already
    present in the canonical deterministic response.
    """
    status = str(response.get("status") or "ok")
    if status != "ok":
        if response.get("resolution"):
            resolution = response["resolution"]
            matches = resolution.get("matches") or []
            lines = [f"I could not resolve the requested format ({status})."]
            if matches:
                lines.append("Possible matches:")
                for row in matches:
                    lines.append(f"- {_display(row.get('label') or row.get('format_id'))}")
            return "\n".join(lines)
        return f"The request could not be completed: {_display(response.get('error'), status)}"

    action = str((response.get("request") or {}).get("action") or "")
    if action == "assess_format_questions":
        return _render_question_assessment(response.get("result") or {})
    if action == "assess_format":
        return _render_single_assessment(response.get("result") or {})
    if action == "list_assessment_questions":
        return _render_question_catalog(response)
    if action == "list_at_risk_formats":
        return _render_at_risk(response)
    if action == "list_evidence_gaps":
        if response.get("result"):
            return _render_evidence_gaps({"results": [response["result"]], "gap_summary": {"formats_with_gaps": 1}})
        return _render_evidence_gaps(response)
    if action == "plan_evidence_remediation":
        if response.get("result"):
            return _render_remediation({"results": [response["result"]], "remediation_summary": {"formats_requiring_remediation": 1, "remediation_item_count": response["result"].get("remediation_item_count", 0)}})
        return _render_remediation(response)
    if action == "search_formats":
        return _render_search(response)
    if action == "assess_format_family":
        rows = response.get("results") or []
        lines = [f"Assessed {len(rows)} format(s)."]
        for row in rows:
            fmt = row.get("format") or {}
            lines.append(
                f"- {_display(fmt.get('label') or fmt.get('format_id'))}: "
                f"{_display(row.get('risk_band'), 'Unbanded')}, evidence {_pct(row.get('evidence_completeness'))}."
            )
        return "\n".join(lines)

    return "The request completed successfully, but no human renderer is defined for this action."
