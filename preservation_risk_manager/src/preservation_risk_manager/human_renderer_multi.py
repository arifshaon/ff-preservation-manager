from __future__ import annotations

from typing import Any

from preservation_risk_manager import human_renderer as base


def _display(value: Any, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


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

        rendered = base.render_human_response(assessment)
        for line in rendered.splitlines():
            lines.append(f"   {line}" if line else "")

    return base._append_ai_disclosure("\n".join(lines), response)


def render_human_response(response: dict[str, Any]) -> str:
    """Render human fan-out responses while delegating all other shapes unchanged."""
    if response.get("human_multi_puid_assessment"):
        return _render_multi_puid(response)
    return base.render_human_response(response)
