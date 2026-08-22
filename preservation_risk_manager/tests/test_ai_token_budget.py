from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIRequest, AIResponse, AIUsage
from preservation_risk_manager.ai.config import AIConfigurationError, AIProviderConfig
from preservation_risk_manager.ai.capability_synthesis import synthesize_with_capabilities
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _BudgetProvider(AIProvider):
    provider_name = "budget-test"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=False)

    def __init__(self, config: AIProviderConfig):
        self.config = config
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "budget-test-model"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "low",
                "confidence": 0.8,
                "rationale": "The retained governed exact-format assessment supports Low concern.",
                "database_evidence_refs": ["R001"],
                "considerations": [
                    {
                        "finding": "The governed exact-format assessment is Low concern.",
                        "basis": "registry_evidence",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["R001"],
                    }
                ],
                "config_rules_considered": ["most_specific_available"],
                "governed_baseline_relation": "same",
                "uncertainty": "Lower-priority evidence may be compacted to respect provider TPM.",
            },
            usage=AIUsage(input_tokens=500, output_tokens=100, total_tokens=600),
        )


def test_tokens_per_minute_is_configurable_and_redacted():
    config = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "tokens_per_minute": 10000,
        "max_output_tokens": 1200,
    })

    assert config.tokens_per_minute == 10000
    assert config.redacted()["tokens_per_minute"] == 10000


def test_tokens_per_minute_must_be_positive():
    try:
        AIProviderConfig.from_dict({"provider": "azure_openai", "tokens_per_minute": 0})
    except AIConfigurationError as exc:
        assert "tokens_per_minute" in str(exc)
    else:
        raise AssertionError("tokens_per_minute=0 must be rejected")


def test_synthesis_compacts_lower_priority_context_to_fit_tpm_budget():
    config = AIProviderConfig.from_dict({
        "provider": "budget-test",
        "tokens_per_minute": 5000,
        "max_output_tokens": 600,
    })
    provider = _BudgetProvider(config)
    policy = load_synthesis_policy()
    source_evidence = [
        {
            "evidence_kind": "source_native_description",
            "source_id": f"source-{index}",
            "source_record_id": f"record-{index}",
            "source_value": "Long preservation context. " * 150,
        }
        for index in range(30)
    ]

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
                "semantic_level": "low",
                "scope_type": "exact_format",
            }
        ],
        criterion_claims=[],
        source_evidence=source_evidence,
        max_evidence_items=100,
    )

    budget = result["token_budget"]
    assert budget["configured_tokens_per_minute"] == 5000
    assert budget["effective_max_output_tokens"] == 600
    assert budget["safety_reserve_tokens"] == 750
    assert budget["prompt_budget_tokens"] == 3650
    assert budget["estimated_prompt_tokens"] <= budget["prompt_budget_tokens"]
    assert budget["evidence_items_available"] == 31
    assert budget["evidence_items_supplied"] < budget["evidence_items_available"]
    assert budget["evidence_items_omitted"] > 0
    assert budget["context_trimmed_for_token_budget"] is True
    assert provider.requests[0].max_output_tokens == 600
    assert any(item["ref"] == "R001" for item in result["database_evidence_refs"])
