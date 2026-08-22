from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
    AIWebCitation,
    AIWebResearchResponse,
)
from preservation_risk_manager.ai.research_synthesis import synthesize_with_web_research
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _PrivacyResearchProvider(AIProvider):
    provider_name = "fake_privacy_research"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    def __init__(self):
        self.research_prompt = ""

    @property
    def model_name(self) -> str:
        return "fake-privacy-model"

    def research_web(self, prompt: str, *, allowed_domains=(), blocked_domains=()):
        self.research_prompt = prompt
        return AIWebResearchResponse(
            provider=self.provider_name,
            model=self.model_name,
            text="Public documentation confirms the format specification remains available.",
            citations=(AIWebCitation("https://example.org/spec", "Public specification"),),
            search_queries=("verify public format specification",),
            consulted_urls=("https://example.org/spec",),
        )

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "low",
                "confidence": 0.8,
                "rationale": "The public evidence confirms the governed baseline.",
                "database_evidence_refs": ["R001", "C001"],
                "web_source_refs": ["W001"],
                "verification_findings": [
                    {
                        "finding": "The public specification remains available.",
                        "relationship_to_database": "confirms",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["C001"],
                        "web_source_refs": ["W001"],
                        "rationale": "The official specification is publicly accessible.",
                    }
                ],
                "policy_rules_applied": ["missing_assessment_policy=exclude"],
                "governed_baseline_relation": "same",
                "uncertainty": "None material for this test.",
            },
            usage=AIUsage(input_tokens=20, output_tokens=20, total_tokens=40),
        )


def test_institution_scoped_claims_and_private_format_fields_are_not_sent_to_web_grounding():
    provider = _PrivacyResearchProvider()
    policy = load_synthesis_policy()

    result = synthesize_with_web_research(
        provider,
        format_context={
            "canonical_id": "puid-fmt-276",
            "label": "PDF 1.7",
            "puids": ["fmt/276"],
            "institution_evidence": [{"secret": "DO-NOT-SEND"}],
            "internal_note": "DO-NOT-SEND-EITHER",
        },
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
        criterion_claims=[
            {
                "source_id": "loc_fdd_xml",
                "source_record_id": "fdd000277",
                "criterion_id": "sustainability.disclosure",
                "value": "openly_documented",
            },
            {
                "source_id": "qnl_internal",
                "source_record_id": "LOCAL-1",
                "criterion_id": "institution.local_capability",
                "value": "internal-sensitive-value",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
            },
        ],
        source_evidence=[
            {
                "evidence_kind": "source_native_description",
                "source_id": "qnl_internal",
                "source_record_id": "LOCAL-RAW-1",
                "source_value": "private-local-description",
                "institution_id": "qnl",
            }
        ],
    )

    assert "PDF 1.7" in provider.research_prompt
    assert "NF00369" in provider.research_prompt
    assert "fdd000277" in provider.research_prompt
    assert "internal-sensitive-value" not in provider.research_prompt
    assert "private-local-description" not in provider.research_prompt
    assert "DO-NOT-SEND" not in provider.research_prompt
    assert result["web_research"]["institution_scoped_evidence_excluded"] == 2
