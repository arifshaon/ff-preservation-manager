from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
)
from preservation_risk_manager.ai.research_synthesis import synthesize_with_capabilities
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _WebOnlyAnswerProvider(AIProvider):
    provider_name = "fake_web_only"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    @property
    def model_name(self) -> str:
        return "fake-web-only-model"

    def generate_with_capabilities(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "moderate",
                "confidence": 0.8,
                "rationale": "The external source suggests moderate concern.",
                "database_evidence_refs": [],
                "considerations": [
                    {
                        "finding": "A current external source reports a preservation concern.",
                        "basis": "external_information",
                        "risk_effect": "raises_concern",
                        "database_evidence_refs": [],
                    }
                ],
                "config_rules_considered": ["missing_assessment_policy=exclude"],
                "governed_baseline_relation": "higher_concern",
                "uncertainty": "The structured response did not explicitly cite the supplied registry evidence.",
            },
            usage=AIUsage(input_tokens=20, output_tokens=20, total_tokens=40),
            metadata={
                "responses_api": True,
                "web_search_used": True,
                "search_queries": ["verify current preservation evidence"],
                "consulted_urls": ["https://example.org/current"],
                "external_sources": [
                    {"url": "https://example.org/current", "title": "Current source"}
                ],
            },
        )

    def generate(self, request: AIRequest) -> AIResponse:
        raise AssertionError("Global capability synthesis should use generate_with_capabilities")


def test_ai_result_that_does_not_explicitly_reference_registry_is_returned_with_warning():
    provider = _WebOnlyAnswerProvider()
    policy = load_synthesis_policy()

    result = synthesize_with_capabilities(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7", "puids": ["fmt/276"]},
        policy=policy,
        governed_synthesis={
            "assessed": True,
            "semantic_level": "low",
            "semantic_label": "Low concern",
        },
        risk_assessments=[
            {
                "source_id": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "native_label": "Low Risk",
                "scope_type": "exact_format",
            }
        ],
        criterion_claims=[],
        source_evidence=[],
    )

    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "moderate"
    assert overall["external_sources"][0]["url"] == "https://example.org/current"
    assert any("did not explicitly reference" in warning for warning in overall["quality_warnings"])
    assert result["governed_synthesis"]["semantic_level"] == "low"
