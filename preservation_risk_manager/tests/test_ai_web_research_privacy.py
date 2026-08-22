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


class _PrivacyResearchProvider(AIProvider):
    provider_name = "fake_privacy_research"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    def __init__(self):
        self.generate_requests: list[AIRequest] = []
        self.capability_requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-privacy-model"

    def generate_with_capabilities(self, request: AIRequest) -> AIResponse:
        self.capability_requests.append(request)
        raise AssertionError("Public web capability must be suppressed for institution-scoped evidence")

    def generate(self, request: AIRequest) -> AIResponse:
        self.generate_requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "low",
                "confidence": 0.8,
                "rationale": "The supplied evidence supports Low concern without public web search.",
                "database_evidence_refs": ["R001", "C001"],
                "considerations": [
                    {
                        "finding": "The public specification evidence remains available in the registry context.",
                        "basis": "registry_evidence",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["C001"],
                    }
                ],
                "config_rules_considered": ["missing_assessment_policy=exclude"],
                "governed_baseline_relation": "same",
                "uncertainty": "Public web search was suppressed because institution-scoped evidence was present.",
            },
            usage=AIUsage(input_tokens=20, output_tokens=20, total_tokens=40),
        )


def test_institution_scoped_evidence_suppresses_public_web_capability_but_still_allows_ai_analysis():
    provider = _PrivacyResearchProvider()
    policy = load_synthesis_policy()

    result = synthesize_with_capabilities(
        provider,
        format_context={
            "canonical_id": "puid-fmt-276",
            "label": "PDF 1.7",
            "puids": ["fmt/276"],
            "institution_evidence": [{"secret": "DO-NOT-SEND-TO-WEB"}],
            "internal_note": "PRIVATE-LOCAL-CONTEXT",
        },
        policy=policy,
        governed_synthesis={
            "assessed": True,
            "semantic_level": "low",
            "semantic_label": "Low concern",
            "contributors": [
                {
                    "source_id": "nara_digital_preservation_framework",
                    "source_record_id": "NF00369",
                    "scope_type": "exact_format",
                    "semantic_level": "low",
                },
                {
                    "source_id": "qnl_internal",
                    "source_record_id": "LOCAL-RISK-1",
                    "scope_type": "institutional_format",
                    "semantic_level": "moderate",
                    "institution_id": "qnl",
                },
            ],
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

    assert len(provider.generate_requests) == 1
    assert provider.capability_requests == []
    external = result["external_capability"]
    assert external["capability_available"] is True
    assert external["capability_invoked"] is False
    assert external["web_search_used"] is False
    assert external["suppressed_for_institution_evidence"] is True
    assert result["overall_synthesized_risk"]["semantic_level"] == "low"
