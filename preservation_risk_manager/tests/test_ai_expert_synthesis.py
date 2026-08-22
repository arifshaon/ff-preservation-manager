from __future__ import annotations

import pytest

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIProviderError, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.expert_synthesis import synthesize_expert_with_ai
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class FakeExpertProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured):
        self.structured = structured
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-expert"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=self.structured,
            usage=AIUsage(input_tokens=120, output_tokens=80, total_tokens=200),
        )


def test_ai_expert_may_be_more_concerned_than_governed_result():
    policy = load_synthesis_policy()
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "method": "config_driven_scope_aware_synthesis",
    }
    provider = FakeExpertProvider({
        "semantic_level": "moderate",
        "confidence": 0.78,
        "rationale": "The governed exact-format evidence is low, but broader preservation knowledge suggests additional ecosystem risk.",
        "database_evidence_refs": ["R001", "C001"],
        "model_knowledge_findings": [
            {
                "finding": "The format remains broadly readable, but long-term preservation depends on maintaining compatible PDF tooling and migration capability.",
                "risk_effect": "raises_concern",
                "confidence": 0.75,
                "temporal_sensitivity": "medium",
            },
            {
                "finding": "The PDF ecosystem has extensive reader and conversion support.",
                "risk_effect": "reduces_concern",
                "confidence": 0.9,
                "temporal_sensitivity": "medium",
            },
        ],
        "config_rules_considered": ["most_specific_available", "broader_scope_context_only"],
        "divergence_explanation": "The expert result incorporates broader model knowledge not represented in the governed source-level assessment.",
        "uncertainty": "The model did not perform live web verification.",
    })

    result = synthesize_expert_with_ai(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
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
        criterion_claims=[
            {
                "source_id": "loc_fdd_xml",
                "source_record_id": "fdd000277",
                "criterion_id": "sustainability.ip_licensing",
                "value": "no_known_barrier",
            }
        ],
        source_evidence=[],
    )

    expert = result["ai_expert_synthesized_risk"]
    assert expert["semantic_level"] == "moderate"
    assert expert["advisory"] is True
    assert expert["authoritative"] is False
    assert expert["live_web_verified"] is False
    assert expert["comparison_to_governed"]["relation"] == "ai_more_concerned"
    assert expert["comparison_to_governed"]["governed_semantic_level"] == "low"
    assert expert["model_knowledge_findings"]
    assert "not perform live web" in expert["currentness_caveat"].lower()
    assert result["governed_synthesis"]["semantic_level"] == "low"


def test_ai_expert_must_reference_only_supplied_database_refs():
    policy = load_synthesis_policy()
    provider = FakeExpertProvider({
        "semantic_level": "moderate",
        "confidence": 0.8,
        "rationale": "Invalid citation.",
        "database_evidence_refs": ["X999"],
        "model_knowledge_findings": [],
        "config_rules_considered": [],
        "divergence_explanation": "",
        "uncertainty": "",
    })

    with pytest.raises(AIProviderError, match="unknown database evidence refs"):
        synthesize_expert_with_ai(
            provider,
            format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
            policy=policy,
            governed_synthesis={"assessed": True, "semantic_level": "low"},
            risk_assessments=[],
            criterion_claims=[],
            source_evidence=[],
        )


def test_expert_policy_allows_model_knowledge_but_not_live_web_claims():
    policy = load_synthesis_policy()
    expert_policy = policy.ai["expert_synthesis"]
    assert expert_policy["allow_model_training_knowledge"] is True
    assert expert_policy["allow_live_web_knowledge"] is False
    assert expert_policy["output_role"] == "parallel_advisory"
    assert expert_policy["governed_result_remains_authoritative"] is True
