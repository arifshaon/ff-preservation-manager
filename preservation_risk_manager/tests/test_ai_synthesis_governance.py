from __future__ import annotations

import pytest

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIProviderError, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.synthesis import synthesize_with_ai
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured):
        self.structured = structured
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-synthesis"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=self.structured,
            usage=AIUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def _dpc_source_evidence():
    return {
        "evidence_kind": "source_native_risk_assessment",
        "source_id": "dpc_bit_list_2025",
        "source_type": "dpc_bit_list",
        "source_record_id": "Lg7_RYL0UI",
        "native_label": "Vulnerable",
        "scope_type": "format_group",
        "scope_name": "PDF",
    }


def test_config_mapped_source_native_risk_is_deterministic_not_ai_interpreted():
    policy = load_synthesis_policy()
    provider = FakeProvider({
        "proposed_overall_level": "moderate",
        "confidence": 0.9,
        "rationale": "The configured DPC assessment is moderate concern.",
        "source_interpretations": [],
        "supporting_evidence_refs": ["R001"],
        "policy_rules_applied": ["dpc-global-bit-list"],
        "uncertainty": "None beyond the source scope.",
    })

    result = synthesize_with_ai(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
        policy=policy,
        risk_assessments=[],
        criterion_claims=[],
        source_evidence=[_dpc_source_evidence()],
    )

    assert result["status"] == "ok"
    assert result["deterministic_synthesis"]["semantic_level"] == "moderate"
    assert result["overall_synthesized_risk"]["semantic_level"] == "moderate"
    assert result["overall_synthesized_risk"]["ai_assisted"] is False
    assert result["overall_synthesized_risk"]["ai_consulted"] is True
    assert result["ai_interpreted_assessments"] == []
    assert len(result["config_normalized_source_assessments"]) == 1
    assert result["config_normalized_source_assessments"][0]["policy_rule_id"] == "dpc-global-bit-list"
    assert all(ref["kind"] != "source_native_risk_assessment" for ref in result["evidence_refs"])
    assert result["evidence_refs"][0]["kind"] == "config_normalized_source_risk_assessment"


def test_ai_cannot_reinterpret_config_normalized_source_risk_reference():
    policy = load_synthesis_policy()
    provider = FakeProvider({
        "proposed_overall_level": "high",
        "confidence": 0.99,
        "rationale": "Attempted reinterpretation.",
        "source_interpretations": [
            {
                "evidence_ref": "R001",
                "semantic_level": "high",
                "rationale": "Attempt to override a configured DPC mapping.",
            }
        ],
        "supporting_evidence_refs": ["R001"],
        "policy_rules_applied": [],
        "uncertainty": "None claimed.",
    })

    with pytest.raises(AIProviderError, match="not an unmapped source_native_risk_assessment"):
        synthesize_with_ai(
            provider,
            format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
            policy=policy,
            risk_assessments=[],
            criterion_claims=[],
            source_evidence=[_dpc_source_evidence()],
        )
