from types import SimpleNamespace

from preservation_risk_manager import integration_cli as base_integration
from preservation_risk_manager.ai.base import AIProviderError
from preservation_risk_manager import integration_cli_human as human_cli


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


def test_rate_limit_stops_batch_ai_but_keeps_all_deterministic_puid_assessments(monkeypatch):
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

    def fake_batch(provider, _reader, _framework, _request, candidates, assessments, **kwargs):
        try:
            provider.generate(object())
        except AIProviderError as exc:
            for assessment in assessments:
                assessment["ai_risk_assessment"] = {
                    "status": "error_deterministic_retained",
                    "ai_mode": "fill-gaps",
                    "reason": "batch_provider_error",
                    "error": str(exc),
                }
        return {
            "provider_call_count": 1,
            "matched_puid_count": len(candidates),
            "failed_error": "429 Too Many Requests",
        }

    monkeypatch.setattr(base_integration, "execute_request", fake_execute)
    monkeypatch.setattr(human_cli, "apply_batched_fill_gaps", fake_batch)

    delegate = RateLimitedDelegate()
    provider = human_cli._RateLimitCircuitProvider(delegate)
    framework = SimpleNamespace(
        framework_id="test",
        version="1",
        calibration_status="calibrated",
        banding_enabled=True,
    )

    response = human_cli._assess_human_puid_matches(
        reader,
        framework,
        request,
        identification,
        provider=provider,
        ai_mode="fill-gaps",
        max_evidence_items=20,
        user_question="What is the risk of PDF?",
    )

    assert response["status"] == "ok"
    assert response["ai_rate_limited"] is True
    assert response["matched_puids"] == ["fmt/18", "fmt/19"]
    assert executed == ["puid-fmt-18", "puid-fmt-19"]
    assert delegate.calls == 1
    assert response["ai_batch"]["provider_call_count"] == 1
    assert all(item["result"]["risk_band"] == "Moderate" for item in response["assessments"])
    assert all(
        item["ai_risk_assessment"]["status"] == "error_deterministic_retained"
        for item in response["assessments"]
    )
