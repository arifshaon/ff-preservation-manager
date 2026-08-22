from __future__ import annotations

import pytest

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIProviderError, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.synthesis import synthesize_with_ai
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    @property
    def model_name(self) -> str:
        return "fake-synthesis"

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "proposed_overall_level": "high",
                "confidence": 0.99,
                "rationale": "Attempted reinterpretation.",
                "source_interpretations": [
                    {
                        "evidence_ref": "S001",
                        "semantic_level": "high",
                        "rationale": "Attempt to override a configured DPC mapping.",
                    }
                ],
                "supporting_evidence_refs": ["S001"],
                "policy_rules_applied": [],
                "uncertainty": "None claimed.",
            },
            usage=AIUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def test_ai_cannot_reinterpret_source_value_already_mapped_by_config():
    policy = load_synthesis_policy()

    with pytest.raises(AIProviderError, match="Configured mappings are binding"):
        synthesize_with_ai(
            FakeProvider(),
            format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
            policy=policy,
            risk_assessments=[],
            criterion_claims=[],
            source_evidence=[
                {
                    "evidence_kind": "source_native_risk_assessment",
                    "source_id": "dpc_bit_list_2025",
                    "source_type": "dpc_bit_list",
                    "source_record_id": "Lg7_RYL0UI",
                    "native_label": "Vulnerable",
                    "scope_type": "format_group",
                    "scope_name": "PDF",
                }
            ],
        )
