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
        "framework_id": "gap_test",
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
                "critical": True,
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
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {"canonical_id": "fmt-pdf", "preferred_name": "PDF", "current": True},
            {"canonical_id": "fmt-unmapped", "preferred_name": "Legacy PDF Variant", "current": True},
            {"canonical_id": "fmt-unrelated", "preferred_name": "Sparse PDF Variant", "current": True},
            {"canonical_id": "fmt-png", "preferred_name": "PNG", "current": True},
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
                "canonical_id": "fmt-unmapped",
                "criterion_id": "sustainability.disclosure",
                "value": "mystery_value",
                "source_id": "b",
            },
            {
                "canonical_id": "fmt-unrelated",
                "criterion_id": "technical.container_complexity",
                "value": "complex",
                "source_id": "c",
            },
        ],
    }))


def test_family_evidence_gap_request_distinguishes_mapping_and_missing_evidence():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "list_evidence_gaps",
            "filters": {"family": "PDF", "risk_bands": []},
            "scope": "global",
            "limit": 100,
        },
    )

    assert result["status"] == "ok"
    assert result["candidate_count"] == 3
    assert result["result_count"] == 2
    assert result["gap_summary"]["fully_covered_formats"] == 1

    by_id = {row["format"]["format_id"]: row for row in result["results"]}
    unmapped = by_id["fmt-unmapped"]
    assert unmapped["gap_classification"] == "mixed_mapping_and_evidence_gaps"
    gaps = {row["question_id"]: row for row in unmapped["missing_questions"]}
    assert gaps["q_disclosure"]["gap_reason"] == "claims_exist_but_do_not_map"
    assert gaps["q_disclosure"]["matched_values"] == ["mystery_value"]
    assert gaps["q_adoption"]["gap_reason"] == "no_matching_evidence"

    unrelated = by_id["fmt-unrelated"]
    assert unrelated["gap_classification"] == "claims_exist_but_not_for_framework"
    assert unrelated["criterion_claims_available"] == 1
    assert unrelated["matched_claims_for_framework"] == 0


def test_single_format_evidence_gap_request_returns_diagnosis():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "list_evidence_gaps",
            "format": "Legacy PDF Variant",
            "scope": "global",
        },
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["result"]["format"]["format_id"] == "fmt-unmapped"
    assert result["result"]["gap_count"] == 2
    assert result["result"]["unmapped_claims_for_framework"] == 1


def test_human_evidence_gap_question_routes_to_family_action():
    provider = FakeRouterProvider({
        "action": "list_evidence_gaps",
        "format": None,
        "query": None,
        "filters": {"family": "PDF", "risk_bands": []},
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    })

    routed = route_natural_language_request(
        provider,
        "Which PDF formats need more evidence and what is missing?",
    )

    assert len(provider.requests) == 1
    assert routed["request"]["action"] == "list_evidence_gaps"
    assert routed["request"]["filters"]["family"] == "PDF"
    assert routed["router"]["repairs"] == []
