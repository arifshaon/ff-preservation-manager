from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.errors import FrameworkError

BAND_ORDER = ["Low", "Moderate", "High"]
POSTURE_TRIAGE_RANK = {
    "Low": 0,
    "Moderate": 1,
    "High": 2,
    "Needs Assessment": 2,
}
READINESS_STATES = [
    "Covered",
    "Partially Covered",
    "Uncovered",
    "Unknown",
    "Not Assessed",
]
ANALYSIS_STATES = ["Low", "Moderate", "High", "Unknown", "Not Assessed"]
EXPOSURE_LEVELS = ["Low", "Moderate", "High", "Unknown"]

DEFAULT_POSTURE_MATRIX: dict[str, dict[str, str]] = {
    "Not Assessed": {"any_readiness": "Needs Assessment"},
    "Unknown": {"any_readiness": "Needs Assessment"},
    "High": {"any_readiness": "High"},
    "Moderate": {
        "Uncovered": "High",
        "Partially Covered": "Moderate",
        "Covered": "Moderate",
        "Unknown": "Needs Assessment",
        "Not Assessed": "Needs Assessment",
    },
    "Low": {
        "Uncovered": "Moderate",
        "Partially Covered": "Low",
        "Covered": "Low",
        "Unknown": "Needs Assessment",
        "Not Assessed": "Needs Assessment",
    },
}


def default_posture_matrix() -> dict[str, dict[str, str]]:
    """Return a mutable copy of the default QNL posture matrix."""
    return deepcopy(DEFAULT_POSTURE_MATRIX)


def _rank_map(order: list[str] | dict[str, int]) -> dict[str, int]:
    if isinstance(order, dict):
        return dict(order)
    return {value: index for index, value in enumerate(order)}


def validate_posture_matrix(
    matrix: dict[str, dict[str, str]],
    *,
    band_order: list[str] | dict[str, int] | None = None,
    posture_order: list[str] | dict[str, int] | None = None,
    analysis_states: list[str] | None = None,
    readiness_states: list[str] | None = None,
) -> None:
    """Validate exhaustiveness and the no-below-band posture invariant.

    Constraint: readiness may escalate local posture, but no configured cell may
    place `local_risk_posture` below the analysed band. Unknown and Not Assessed
    bands are exempt from the numeric floor because they map to Needs Assessment.
    """
    band_rank = _rank_map(band_order or BAND_ORDER)
    posture_rank = _rank_map(posture_order or POSTURE_TRIAGE_RANK)
    analysis_states = analysis_states or ANALYSIS_STATES
    readiness_states = readiness_states or READINESS_STATES

    for band in analysis_states:
        if band not in matrix:
            raise FrameworkError(f"Posture matrix missing analysed band: {band}")
        readiness_map = matrix[band]
        for readiness in readiness_states:
            posture = readiness_map.get(readiness, readiness_map.get("any_readiness"))
            if posture is None:
                raise FrameworkError(f"Posture matrix has no value for {band}/{readiness}")
            if posture not in posture_rank:
                raise FrameworkError(f"Posture matrix uses unknown posture value: {posture}")
            if band not in band_rank:
                continue
            floor = band_rank[band]
            if posture_rank[posture] < floor:
                raise FrameworkError(
                    f"{band}/{readiness} -> {posture} violates the readiness escalation constraint: "
                    "posture may not fall below the analysed band"
                )


def compute_local_risk_posture(
    analysed_band: str | None,
    readiness_status: str | None,
    *,
    exposure_level: str | None = None,
    matrix: dict[str, dict[str, str]] | None = None,
) -> str:
    """Return the QNL local posture for an analysed band and readiness state.

    Exposure is intentionally accepted but not used to mutate posture. Exposure
    belongs in triage ranking and queueing, not in the posture matrix; a high
    volume of well-covered low-risk formats should not become higher posture just
    because the holdings are large.
    """
    matrix = matrix or DEFAULT_POSTURE_MATRIX
    validate_posture_matrix(matrix)
    band = analysed_band or "Not Assessed"
    readiness = readiness_status or "Unknown"
    readiness_map = matrix.get(band) or matrix["Not Assessed"]
    return readiness_map.get(readiness) or readiness_map.get("any_readiness") or "Needs Assessment"


def triage_rank(posture: str, *, exposure_level: str | None = None) -> tuple[int, int]:
    """Return a sortable triage rank while keeping posture visually distinct.

    Needs Assessment ranks alongside High for work-queue triage, but the posture
    value remains distinct and must not be rendered as an assessed High risk.
    Exposure can raise ordering within the same posture bucket without changing
    posture itself.
    """
    exposure_rank = {"Low": 0, "Moderate": 1, "Unknown": 1, "High": 2}
    return (
        POSTURE_TRIAGE_RANK.get(posture, POSTURE_TRIAGE_RANK["Needs Assessment"]),
        exposure_rank.get(exposure_level or "Unknown", 1),
    )
