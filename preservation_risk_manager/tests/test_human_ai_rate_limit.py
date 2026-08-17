from types import SimpleNamespace

from preservation_risk_manager import integration_cli as base_integration
from preservation_risk_manager.ai.base import AIProviderError
from preservation_risk_manager.integration_cli_human import (
    _RateLimitCircuitProvider,
    _assess_human_puid_matches,
)


class FakeReader:
    def __init__(self, rows):
        self.rows = list(rows)

    def list_canonical_formats(self):
        return list(self.rows)


class RateLimitedDelegate:
    provider_name = "azure_openai"
    model_name = "test-deployment"

    def __init__(self):
        self.calls = 0

    def describe(self):
        return {"provider": self.provider_name, "model": self.model_name}

    def generate(self, request):
        self.calls += 1
        raise AIProviderError("Azure OpenAI request failed: 429 Too Many Requests")


def _rows():
    return [
        {
            "canonical_id": "puid-fmt-18",
            "preferred_name": "PDF 1.4",
            "identifiers": {"puid": ["fmt/18"]},
        },
        {
            "canonical_id": "puid-fmt-19",
            "preferred_name": "PDF 1.5",
            "identifiers": {"puid": ["fmt/19"]},
        },
    ]


def test_rate_limit_stops_ai_calls_but_keeps_all_deterministic_puid_assessments(monkeypatch):
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
        ],
    }

    executed = []
    ai_apply_calls = []

    def fake_execute(_reader, _framework, candidate_request):
        executed.append(candidate_request["format"])
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

    def fake_apply(_reader, _framework, _request, response, *, provider, ai_mode, **kwargs):
        ai_apply_calls.append(_request["format"])
        try:
            provider.generate(object())
        except AIProviderError:
            pass
        response["ai_risk_assessment"] = {
            "status": "ok",
            "ai_mode": ai_mode,
            "provider": provider.describe(),
        }
        return response

    monkeypatch.setattr(base_integration, "execute_request", fake_execute)
    monkeypatch.setattr(base_integration, "_apply_ai_risk_assessment", fake_apply)

    delegate = RateLimitedDelegate()
    provider = _RateLimitCircuitProvider(delegate)
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
        provider=provider,
        ai_mode="fill-gaps",
        max_evidence_items=20,
    )

    assert response["status"] == "ok"
    assert response["ai_rate_limited"] is True
    assert response["matched_puids"] == ["fmt/18", "fmt/19"]
    assert executed == ["puid-fmt-18", "puid-fmt-19"]

    # Only the first PUID is allowed to reach the network-backed AI path.
    assert ai_apply_calls == ["puid-fmt-18"]
    assert delegate.calls == 1

    first, second = response["assessments"]
    assert first["ai_risk_assessment"]["status"] == "partial_rate_limited"
    assert second["ai_risk_assessment"]["status"] == "skipped_rate_limited"
    assert second["result"]["risk_band"] == "Moderate"
