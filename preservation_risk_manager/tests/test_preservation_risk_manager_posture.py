from __future__ import annotations

import pytest

from preservation_risk_manager.errors import FrameworkError
from preservation_risk_manager.posture import (
    ANALYSIS_STATES,
    EXPOSURE_LEVELS,
    READINESS_STATES,
    compute_local_risk_posture,
    default_posture_matrix,
    triage_rank,
    validate_posture_matrix,
)


def test_posture_matrix_is_exhaustive_for_supported_inputs():
    for band in ANALYSIS_STATES:
        for readiness in READINESS_STATES:
            for exposure in EXPOSURE_LEVELS:
                posture = compute_local_risk_posture(band, readiness, exposure_level=exposure)
                assert posture in {"Low", "Moderate", "High", "Needs Assessment"}


def test_posture_validator_rejects_cell_below_analysed_band():
    matrix = default_posture_matrix()
    matrix["High"] = {"any_readiness": "Low"}

    with pytest.raises(FrameworkError, match="posture may not fall below the analysed band"):
        validate_posture_matrix(matrix)


def test_unassessed_formats_get_needs_assessment_posture():
    assert compute_local_risk_posture(None, None) == "Needs Assessment"
    assert compute_local_risk_posture("Not Assessed", "Covered") == "Needs Assessment"
    assert compute_local_risk_posture("Unknown", "Uncovered") == "Needs Assessment"


def test_needs_assessment_ranks_with_high_but_remains_distinct():
    assert triage_rank("Needs Assessment")[0] == triage_rank("High")[0]
    assert "Needs Assessment" != "High"


def test_exposure_does_not_mutate_posture_for_well_covered_low_risk_format():
    assert compute_local_risk_posture("Low", "Covered", exposure_level="High") == "Low"
    assert triage_rank("Low", exposure_level="High") > triage_rank("Low", exposure_level="Low")
