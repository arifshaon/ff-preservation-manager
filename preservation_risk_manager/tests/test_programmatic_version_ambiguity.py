from preservation_risk_manager.integration_cli import _promote_version_ambiguity


def _metadata(query):
    return {
        "input": query,
        "status": "not_found",
        "match_type": None,
        "method": "ai_fallback_no_match",
        "ai": {
            "status": "no_match",
            "confidence": 0.9,
            "candidate_canonical_ids": [],
            "candidates": [
                {
                    "canonical_id": "puid-fmt-505",
                    "label": "Adobe Flash",
                    "version": "8",
                    "identifiers": {"extension": ["swf"], "puid": ["fmt/505"]},
                },
                {
                    "canonical_id": "puid-fmt-506",
                    "label": "Adobe Flash",
                    "version": "9",
                    "identifiers": {"extension": ["swf"], "puid": ["fmt/506"]},
                },
            ],
        },
    }


def test_generic_swf_no_match_becomes_version_ambiguity():
    result = _promote_version_ambiguity(_metadata("Adobe Shockwave Flash SWF file"))
    assert result["status"] == "ambiguous"
    assert result["match_type"] == "programmatic_version_ambiguity"
    assert set(result["ambiguity_candidate_canonical_ids"]) == {"puid-fmt-505", "puid-fmt-506"}
    assert result["ai"]["status"] == "no_match"


def test_explicit_swf_version_is_not_promoted_to_generic_ambiguity():
    result = _promote_version_ambiguity(_metadata("Adobe Shockwave Flash SWF version 8"))
    assert result["status"] == "not_found"
    assert "programmatic_ambiguity" not in result
