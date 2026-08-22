from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.synthesis import synthesize_with_ai
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self):
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-synthesis"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "proposed_overall_level": "low",
                "confidence": 0.95,
                "rationale": "The exact-format configured assessment is Low; broader PDF-group evidence is context.",
                "source_interpretations": [],
                "supporting_evidence_refs": ["R001", "R002"],
                "policy_rules_applied": ["most_specific_available"],
                "uncertainty": "The DPC assessment is broader in scope.",
            },
            usage=AIUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def test_governed_nara_duplicate_from_source_records_is_not_an_ai_candidate():
    """The legacy bounded helper must suppress governed source-record duplicates.

    Overall product synthesis now uses the capability-driven path, which always
    consults the configured AI provider. This lower-level helper is retained for
    bounded mapping-gap workflows and correctly skips the provider when policy
    already resolves all source-level risk.
    """
    policy = load_synthesis_policy()
    provider = FakeProvider()

    result = synthesize_with_ai(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7"},
        policy=policy,
        risk_assessments=[
            {
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "native_label": "Low Risk",
                "scope_type": "exact_format",
            },
            {
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "source_record_id": "Lg7_RYL0UI",
                "native_label": "Vulnerable",
                "scope_type": "format_group",
                "scope_name": "PDF",
            },
        ],
        criterion_claims=[],
        source_evidence=[
            {
                "evidence_kind": "source_native_risk_assessment",
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "native_label": "Low Risk",
                "native_score": 24.0,
            }
        ],
    )

    assert result["status"] == "skipped_no_ai_work_required"
    assert provider.requests == []
    assert result["suppressed_configured_source_risk_duplicates"] == 1
    assert result["config_normalized_source_assessments"] == []
    assert result["ai_interpreted_assessments"] == []
    assert result["overall_synthesized_risk"]["semantic_level"] == "low"
    assert result["overall_synthesized_risk"]["ai_assisted"] is False
    assert result["overall_synthesized_risk"]["ai_consulted"] is False
