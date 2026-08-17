from types import SimpleNamespace

import pytest

from preservation_risk_manager import integration_cli as base_integration
from preservation_risk_manager.ai.base import AIConfigurationError
from preservation_risk_manager.ai.config import AIProviderConfig
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.integration_cli_human import _assess_human_puid_matches


class FakeReader:
    def __init__(self, rows):
        self.rows = list(rows)

    def list_canonical_formats(self):
        return list(self.rows)


class FakeProvider:
    provider_name = "test"
    model_name = "test-model"
    rate_limited = False

    def describe(self):
        return {"provider": self.provider_name, "model": self.model_name}


def _rows():
    return [
        {
            "canonical_id": f"puid-fmt-{number}",
            "preferred_name": f"PDF test {number}",
            "identifiers": {"puid": [f"fmt/{number}"]},
        }
        for number in (18, 19, 20)
    ]


def test_ai_config_defaults_human_format_limit_to_ten_and_accepts_override():
    assert AIProviderConfig.from_dict({"provider": "mock"}).human_ai_format_limit == 10
    assert AIProviderConfig.from_dict({"provider": "mock", "human_ai_format_limit": 4}).human_ai_format_limit == 4

    with pytest.raises(AIConfigurationError):
        AIProviderConfig.from_dict({"provider": "mock", "human_ai_format_limit": 0})


def test_broad_human_query_limits_ai_to_configured_number_but_keeps_all_deterministic(monkeypatch):
    reader = FakeReader(_rows())
    request = {
        "action": "assess_format",
        "format": "PDF",
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    }
    identification = {
        "status": "resolved",
        "match_type": "name",
        "resolved_canonical_id": "puid-fmt-18",
        "resolved_label": "PDF",
        "matched_candidates": [
            {"canonical_id": "puid-fmt-18"},
            {"canonical_id": "puid-fmt-19"},
            {"canonical_id": "puid-fmt-20"},
        ],
    }

    deterministic_calls = []
    ai_calls = []

    def fake_execute(_reader, _framework, candidate_request):
        deterministic_calls.append(candidate_request["format"])
        return {
            "status": "ok",
            "request": dict(candidate_request),
            "result": {
                "format": {
                    "format_id": candidate_request["format"],
                    "label": candidate_request["format"],
                },
                "risk_band": "Moderate",
                "score": 5,
                "max_score": 10,
                "analysis_status": "Complete",
                "evidence_completeness": 1.0,
                "main_risk_factors": [],
                "missing_count": 0,
                "abstention_count": 0,
                "banding_enabled": True,
            },
        }

    def fake_apply(_reader, _framework, candidate_request, response, *, ai_mode, **kwargs):
        ai_calls.append(candidate_request["format"])
        response["ai_risk_assessment"] = {
            "status": "ok",
            "ai_mode": ai_mode,
            "provider": {"provider": "test"},
        }
        return response

    monkeypatch.setattr(base_integration, "execute_request", fake_execute)
    monkeypatch.setattr(base_integration, "_apply_ai_risk_assessment", fake_apply)

    framework = SimpleNamespace(
        framework_id="test",
        version="1",
        calibration_status="calibrated",
        banding_enabled=True,
    )
    response = _assess_human_puid_matches(
        reader,
        framework,
        request,
        identification,
        provider=FakeProvider(),
        ai_mode="review-all",
        max_evidence_items=20,
        ai_format_limit=2,
    )

    assert deterministic_calls == ["puid-fmt-18", "puid-fmt-19", "puid-fmt-20"]
    assert ai_calls == ["puid-fmt-18", "puid-fmt-19"]
    assert response["matched_puid_count"] == 3
    assert response["ai_format_limit"] == 2
    assert response["ai_format_limit_applied"] is True
    assert response["ai_formats_assessed"] == 2
    assert response["ai_formats_skipped"] == 1
    assert response["assessments"][2]["ai_risk_assessment"]["status"] == "skipped_format_limit"

    rendered = render_human_response(response)
    assert "More than 2 matching formats were found" in rendered
    assert "first 2 PUIDs" in rendered
    assert "remaining 1 PUIDs" in rendered
