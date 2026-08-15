from __future__ import annotations

from typing import Any

_LOCAL_FIELDS = {"readiness_status", "exposure_level", "local_risk_posture", "recommended_actions"}


def build_global_response(*, format_label: str, analysed_band: str | None, analysis_status: str) -> dict[str, Any]:
    """Build a global-only response shape without institution-local null fields."""
    return {
        "format": format_label,
        "scope": "global",
        "analysed_band": analysed_band,
        "analysis_status": analysis_status,
    }


def build_institution_response(
    *,
    format_label: str,
    institution_id: str,
    analysed_band: str | None,
    analysis_status: str,
    readiness_status: str,
    exposure_level: str,
    local_risk_posture: str,
    recommended_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "format": format_label,
        "scope": "institution",
        "institution_id": institution_id,
        "analysed_band": analysed_band,
        "analysis_status": analysis_status,
        "readiness_status": readiness_status,
        "exposure_level": exposure_level,
        "local_risk_posture": local_risk_posture,
        "recommended_actions": recommended_actions or [],
    }


def has_local_fields(response: dict[str, Any]) -> bool:
    return any(field in response for field in _LOCAL_FIELDS)
