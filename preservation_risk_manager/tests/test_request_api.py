from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
)
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.request_api import execute_request


class FakeRouterProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured):
        self.structured = structured
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-router"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=self.structured,
            usage=AIUsage(input_tokens=20, output_tokens=10, total_tokens=30),
        )


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "request_test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.5,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 1},
                {"band": "Moderate", "min_score": 2, "max_score": 4},
                {"band": "High", "min_score": 5, "max_score": 10},
            ],
        },
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Documented?",
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "limited_or_unclear_specification", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_adoption",
                "label": "Adopted?",
                "evidence_fields": ["sustainability.adoption"],
                "answers": [
                    {"id": "widely_adopted", "points": 0},
                    {"id": "niche_or_declining", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
        ],
    })


def _reader() -> RegistryReader:
    store = JsonRegistryStore({
        "canonical_formats": [
            {
                "canonical_id": "fmt-pdf",
                "preferred_name": "PDF",
                "extensions": ["pdf"],
                "current": True,
            },
            {
                "canonical_id": "fmt-legacy-pdf",
                "preferred_name": "Legacy PDF Variant",
                "extensions": ["pdfx"],
                "current": True,
            },
            {
                "canonical_id": "fmt-png",
                "preferred_name": "PNG",
                "extensions": ["png"],
                "current": True,
            },
        ],
        "criterion_claims": [
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "a",
            },
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.adoption",
                "value": "high",
                "source_id": "a",
            },
            {
                "canonical_id": "fmt-legacy-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "limited",
                "source_id": "b",
            },
            {
                "canonical_id": "fmt-legacy-pdf",
                "criterion_id": "sustainability.adoption",
                "value": "low",
                "source_id": "b",
            },
        ],
    })
    return RegistryReader(store=store)


def test_structured_request_lists_only_high_risk_pdf_family_members():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "list_at_risk_formats",
            "filters": {"family": "PDF", "risk_bands": ["High"]},
            "scope": "global",
            "limit": 100,
        },
    )

    assert result["status"] == "ok"
    assert result["candidate_count"] == 2
    assert result["result_count"] == 1
    assert result["results"][0]["format"]["format_id"] == "fmt-legacy-pdf"
    assert result["results"][0]["risk_band"] == "High"
    assert result["results"][0]["score"] == 7


def test_assess_format_returns_canonical_json_result():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "assess_format",
            "format": "fmt-pdf",
            "scope": "global",
        },
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["result"]["format"]["format_id"] == "fmt-pdf"
    assert result["result"]["risk_band"] == "Low"
    assert result["result"]["evidence_completeness"] == 1.0


def test_human_question_routes_to_same_structured_request_shape():
    provider = FakeRouterProvider({
        "action": "list_at_risk_formats",
        "format": None,
        "query": None,
        "filters": {"family": "PDF", "risk_bands": ["Moderate", "High"]},
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    })

    routed = route_natural_language_request(
        provider,
        "Give me the PDF formats that are at risk",
    )

    assert len(provider.requests) == 1
    assert routed["request"]["action"] == "list_at_risk_formats"
    assert routed["request"]["filters"]["family"] == "PDF"
    assert routed["request"]["filters"]["risk_bands"] == ["Moderate", "High"]
    assert routed["router"]["usage"]["total_tokens"] == 30


def test_qnl_default_scope_is_applied_after_routing():
    provider = FakeRouterProvider({
        "action": "assess_format",
        "format": "PDF",
        "query": None,
        "filters": {"family": None, "risk_bands": []},
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    })

    routed = route_natural_language_request(
        provider,
        "What is the risk of PDF?",
        default_scope="institution",
        default_institution_id="qnl",
    )

    assert routed["request"]["scope"] == "institution"
    assert routed["request"]["institution_id"] == "qnl"
