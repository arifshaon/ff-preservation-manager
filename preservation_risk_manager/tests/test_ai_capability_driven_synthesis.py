from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.research_synthesis import synthesize_with_capabilities
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _NoWebProvider(AIProvider):
    provider_name = "fake_no_web"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=False)

    def __init__(self):
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-no-web"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "low",
                "confidence": 0.8,
                "rationale": "The supplied registry evidence supports Low concern.",
                "database_evidence_refs": ["R001"],
                "external_source_refs": [],
                "considerations": [
                    {
                        "finding": "The exact-format source assessment is Low concern.",
                        "basis": "registry_evidence",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["R001"],
                        "external_source_refs": [],
                    }
                ],
                "config_rules_considered": ["most_specific_available"],
                "governed_baseline_relation": "same",
                "uncertainty": "No external search capability was available.",
            },
            usage=AIUsage(input_tokens=50, output_tokens=30, total_tokens=80),
        )


def test_ai_is_still_consulted_when_config_resolves_risk_and_provider_has_no_web():
    provider = _NoWebProvider()
    policy = load_synthesis_policy()
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "method": "config_driven_scope_aware_synthesis",
    }

    result = synthesize_with_capabilities(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7", "puids": ["fmt/276"]},
        policy=policy,
        governed_synthesis=governed,
        risk_assessments=[
            {
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "native_label": "Low Risk",
                "scope_type": "exact_format",
            }
        ],
        criterion_claims=[],
        source_evidence=[],
    )

    assert len(provider.requests) == 1
    assert result["status"] == "ok"
    assert result["mode"] == "capability_driven_ai_synthesis"
    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "low"
    assert overall["governed_baseline"]["semantic_level"] == "low"
    assert overall["capabilities_available"]["web_search"] is False
    assert overall["capabilities_used"]["web_search"] is False
    assert result["external_capability"]["capability_available"] is False
