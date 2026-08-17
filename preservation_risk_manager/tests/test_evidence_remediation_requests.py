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
        "framework_id": "remediation_test",
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


def test_family_remediation_plan_separates_mapping_evidence_and_alignment_work():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "plan_evidence_remediation",
            "filters": {"family": "PDF", "risk_bands": []},
            "scope": "global",
            "limit": 100,
        },
    )

    assert result["status"] == "ok"
    assert result["candidate_count"] == 3
    assert result["result_count"] == 2
    summary = result["remediation_summary"]
    assert summary["formats_requiring_remediation"] == 2
    assert summary["formats_without_remediation"] == 1
    assert summary["action_type_counts"] == {
        "framework_alignment_review": 1,
        "mapping_rule_needed": 1,
        "source_evidence_needed": 3,
    }

    by_id = {row["format"]["format_id"]: row for row in result["results"]}
    unmapped_items = by_id["fmt-unmapped"]["remediation_items"]
    disclosure = next(item for item in unmapped_items if item.get("question_id") == "q_disclosure")
    adoption = next(item for item in unmapped_items if item.get("question_id") == "q_adoption")
    assert disclosure["action_type"] == "mapping_rule_needed"
    assert disclosure["priority"] == "P1"
    assert disclosure["observed_values"] == ["mystery_value"]
    assert adoption["action_type"] == "source_evidence_needed"
    assert adoption["priority"] == "P3"

    unrelated_items = by_id["fmt-unrelated"]["remediation_items"]
    assert any(item["action_type"] == "framework_alignment_review" for item in unrelated_items)


def test_single_format_remediation_plan_returns_no_actions_when_fully_covered():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "plan_evidence_remediation",
            "format": "PDF",
            "scope": "global",
        },
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["result"]["format"]["format_id"] == "fmt-pdf"
    assert result["result"]["remediation_item_count"] == 0
    assert result["result"]["action_type_counts"] == {}


def test_human_remediation_question_routes_to_family_plan():
    provider = FakeRouterProvider({
        "action": "plan_evidence_remediation",
        "format": None,
        "query": None,
        "filters": {"family": "PDF", "risk_bands": []},
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    })

    routed = route_natural_language_request(
        provider,
        "What should we fix first so the PDF family can be assessed?",
    )

    assert len(provider.requests) == 1
    assert routed["request"]["action"] == "plan_evidence_remediation"
    assert routed["request"]["filters"]["family"] == "PDF"
    assert routed["router"]["repairs"] == []
