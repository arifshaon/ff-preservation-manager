from types import SimpleNamespace

from preservation_risk_manager.integration_cli import _identification_ambiguity_response


def test_identification_ambiguity_stops_before_risk_assessment():
    framework = SimpleNamespace(
        framework_id="test-framework",
        version="1.0",
        calibration_status="calibrated",
        banding_enabled=True,
    )
    request = {
        "action": "assess_format",
        "format": "Adobe Shockwave Flash SWF file",
        "scope": "global",
    }
    identification = {
        "input": "Adobe Shockwave Flash SWF file",
        "status": "ambiguous",
        "match_type": "ai_candidate_ambiguity",
        "method": "ai_fallback_ambiguous",
        "ai_attempted": True,
        "ai": {
            "status": "ambiguous",
            "candidate_canonical_ids": ["puid-fmt-505", "puid-fmt-506"],
            "candidates": [
                {
                    "canonical_id": "puid-fmt-505",
                    "label": "Adobe Flash",
                    "version": "8",
                    "identifiers": {"puid": ["fmt/505"]},
                },
                {
                    "canonical_id": "puid-fmt-506",
                    "label": "Adobe Flash",
                    "version": "9",
                    "identifiers": {"puid": ["fmt/506"]},
                },
                {
                    "canonical_id": "unrelated",
                    "label": "Other format",
                },
            ],
        },
    }

    response = _identification_ambiguity_response(framework, request, identification)

    assert response is not None
    assert response["status"] == "ambiguous"
    assert response["resolution"]["status"] == "ambiguous"
    assert response["resolution"]["match_type"] == "ai_candidate_ambiguity"
    assert {row["canonical_id"] for row in response["resolution"]["matches"]} == {
        "puid-fmt-505",
        "puid-fmt-506",
    }
    assert response["risk_assessment"] == {
        "status": "not_run",
        "reason": "canonical_format_not_uniquely_resolved",
    }
