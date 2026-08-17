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
    lines = [
        f"Preservation-risk assessments for {len(assessments)} matched PRONOM PUIDs",
        "",
        "Each matched PUID was assessed independently; no family-level risk score was invented.",
    ]

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
