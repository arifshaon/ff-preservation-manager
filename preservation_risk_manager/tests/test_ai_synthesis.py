from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.synthesis import synthesize_with_ai
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class FakeSynthesisProvider(AIProvider):
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
            usage=AIUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        )


def test_ai_cannot_override_configured_scope_result_without_new_interpreted_risk():
    policy = load_synthesis_policy()
    provider = FakeSynthesisProvider({
        "proposed_overall_level": "moderate",
        "confidence": 0.8,
        "rationale": "Broader DPC context is moderate.",
        "source_interpretations": [],
        "supporting_evidence_refs": ["R001", "R002"],
        "policy_rules_applied": ["most_specific_available"],
        "uncertainty": "DPC is broader scope.",
    })

    result = synthesize_with_ai(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
        policy=policy,
        risk_assessments=[
            {
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "native_label": "Low Risk",
                "scope_type": "exact_format",
            },
            {
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "native_label": "Vulnerable",
                "scope_type": "format_group",
            },
        ],
        criterion_claims=[],
        source_evidence=[],
    )

    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "low"
    assert overall["ai_proposed_overall_level"] == "moderate"
    assert overall["ai_proposal_matches_policy_result"] is False
    assert overall["ai_assisted"] is False


def test_ai_can_normalize_new_unmapped_source_then_config_recomputes_headline():
    policy = load_synthesis_policy()
    provider = FakeSynthesisProvider({
        "proposed_overall_level": "high",
        "confidence": 0.9,
        "rationale": "The new exact-format source explicitly describes severe preservation risk.",
        "source_interpretations": [
            {
                "evidence_ref": "S001",
                "semantic_level": "high",
                "rationale": "The source-native risk finding is explicitly severe/high concern.",
            }
        ],
        "supporting_evidence_refs": ["R001", "S001"],
        "policy_rules_applied": ["highest_semantic_concern"],
        "uncertainty": "The new source has no reviewed normalization rule yet.",
    })

    result = synthesize_with_ai(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
        policy=policy,
        risk_assessments=[
            {
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "native_label": "Low Risk",
                "scope_type": "exact_format",
            }
        ],
        criterion_claims=[],
        source_evidence=[
            {
                "evidence_kind": "source_native_risk_assessment",
                "source_id": "new_source",
                "source_type": "new_source_type",
                "source_record_id": "NEW-1",
                "native_label": "Severe",
                "native_scale": "new_source_scale",
                "scope_type": "exact_format",
                "scope_name": "PDF 1.7",
                "source_value": {"classification": "Severe"},
            }
        ],
    )

    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "high"
    assert overall["ai_assisted"] is True
    assert overall["ai_proposal_matches_policy_result"] is True
    assert any(item.get("source_id") == "new_source" for item in overall["contributors"])
    assert overall["numeric_aggregation"] == "forbidden_across_source_scales"


def test_ai_may_synthesize_from_supporting_evidence_only_when_no_mapped_source_risk_exists():
    policy = load_synthesis_policy()
    provider = FakeSynthesisProvider({
        "proposed_overall_level": "moderate",
        "confidence": 0.65,
        "rationale": "The cited sustainability evidence indicates moderate preservation concern.",
        "source_interpretations": [],
        "supporting_evidence_refs": ["C001"],
        "policy_rules_applied": ["supporting_evidence_policy"],
        "uncertainty": "No source publishes an overall risk assessment for this format.",
    })

    result = synthesize_with_ai(
        provider,
        format_context={"canonical_id": "loc-fdd-test", "label": "Example Format"},
        policy=policy,
        risk_assessments=[],
        criterion_claims=[
            {
                "canonical_id": "loc-fdd-test",
                "criterion_id": "sustainability.adoption",
                "value": "limited_adoption",
                "source_id": "loc",
            }
        ],
        source_evidence=[],
    )

    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "moderate"
    assert overall["method"] == "ai_policy_guided_supporting_evidence_synthesis"
    assert overall["supporting_evidence_refs"] == ["C001"]
    assert overall["missing_evidence_policy"] == "exclude"
