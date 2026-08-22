from __future__ import annotations

import pytest

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIUsage,
    AIWebCitation,
    AIWebResearchResponse,
)
from preservation_risk_manager.ai.research_synthesis import synthesize_with_web_research
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _WebOnlyAnswerProvider(AIProvider):
    provider_name = "fake_web_only"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    @property
    def model_name(self) -> str:
        return "fake-web-only-model"

    def research_web(self, prompt: str, *, allowed_domains=(), blocked_domains=()):
        return AIWebResearchResponse(
            provider=self.provider_name,
            model=self.model_name,
            text="A current public source provides additional preservation information.",
            citations=(AIWebCitation("https://example.org/current", "Current source"),),
            search_queries=("verify current preservation evidence",),
            consulted_urls=("https://example.org/current",),
        )

    def generate(self, request: AIRequest) -> AIResponse:
        # Deliberately invalid: the model ignores the supplied registry evidence
        # and bases its assessed result solely on W001.
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "moderate",
                "confidence": 0.8,
                "rationale": "The web source suggests moderate concern.",
                "database_evidence_refs": [],
                "web_source_refs": ["W001"],
                "verification_findings": [
                    {
                        "finding": "A current web source reports a preservation concern.",
                        "relationship_to_database": "supplements",
                        "risk_effect": "raises_concern",
                        "database_evidence_refs": [],
                        "web_source_refs": ["W001"],
                        "rationale": "This finding comes from the web source only.",
                    }
                ],
                "policy_rules_applied": ["missing_assessment_policy=exclude"],
                "governed_baseline_relation": "higher_concern",
                "uncertainty": "The registry evidence was not considered by this deliberately invalid response.",
            },
            usage=AIUsage(input_tokens=20, output_tokens=20, total_tokens=40),
        )


def test_web_researched_assessment_cannot_ignore_available_registry_evidence():
    provider = _WebOnlyAnswerProvider()
    policy = load_synthesis_policy()

    with pytest.raises(AIProviderError, match="must cite registry/database evidence"):
        synthesize_with_web_research(
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
