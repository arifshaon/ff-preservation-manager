from __future__ import annotations

from types import SimpleNamespace

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
    AIWebCitation,
    AIWebResearchResponse,
)
from preservation_risk_manager.ai.config import AIProviderConfig
from preservation_risk_manager.ai.providers.azure_openai import AzureOpenAIProvider
from preservation_risk_manager.ai.research_synthesis import synthesize_with_capabilities
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _FakeResponsesAPI:
    def __init__(self, *, use_web: bool = True):
        self.payload = None
        self.use_web = use_web

    def create(self, **payload):
        self.payload = payload
        output = []
        if self.use_web:
            output.extend([
                {
                    "type": "web_search_call",
                    "action": {
                        "query": "PDF 1.7 official current reader support specification",
                        "sources": [{"url": "https://example.org/spec"}],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.org/spec",
                                    "title": "Official specification",
                                }
                            ]
                        }
                    ],
                },
            ])
        return SimpleNamespace(
            model="test-deployment",
            output_text="The supplied evidence has been analysed; external search was used only if useful.",
            output=output,
            usage=SimpleNamespace(input_tokens=50, output_tokens=30, total_tokens=80),
        )


class _FakeResponsesClient:
    def __init__(self, *, use_web: bool = True):
        self.responses = _FakeResponsesAPI(use_web=use_web)


def _azure_config(**extra):
    data = {
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "api_key": "test-key",
        "deployment": "test-deployment",
    }
    data.update(extra)
    return AIProviderConfig.from_dict(data)


def test_azure_provider_exposes_web_search_with_auto_tool_choice_without_enable_switch():
    config = _azure_config(external_research={"allowed_domains": ["example.org"]})
    responses_client = _FakeResponsesClient(use_web=True)
    provider = AzureOpenAIProvider(config, client=object(), responses_client=responses_client)

    result = provider.research_web("Analyse the supplied PDF evidence and use available capabilities where useful.")

    assert result.metadata["web_search_used"] is True
    assert result.citations[0].url == "https://example.org/spec"
    payload = responses_client.responses.payload
    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["type"] == "web_search"
    assert payload["tools"][0]["filters"]["allowed_domains"] == ["example.org"]


def test_azure_provider_allows_model_to_decline_web_search():
    config = _azure_config()
    responses_client = _FakeResponsesClient(use_web=False)
    provider = AzureOpenAIProvider(config, client=object(), responses_client=responses_client)

    result = provider.research_web("Analyse the supplied evidence; use web search only if useful.")

    assert result.text
    assert result.metadata["web_search_used"] is False
    assert result.citations == ()
    assert responses_client.responses.payload["tool_choice"] == "auto"


class _FakeCapabilityProvider(AIProvider):
    provider_name = "fake_capability"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    def __init__(self, *, use_web: bool):
        self.use_web = use_web
        self.research_prompts: list[str] = []
        self.synthesis_requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-capability-model"

    def research_web(self, prompt: str, *, allowed_domains=(), blocked_domains=()):
        self.research_prompts.append(prompt)
        citations = (
            (AIWebCitation("https://example.org/current-tooling", "Current tooling"),)
            if self.use_web else ()
        )
        return AIWebResearchResponse(
            provider=self.provider_name,
            model=self.model_name,
            text="The supplied registry evidence was analysed with the capabilities available to the model.",
            citations=citations,
            search_queries=("current PDF tooling",) if self.use_web else (),
            consulted_urls=("https://example.org/current-tooling",) if self.use_web else (),
            metadata={"web_search_used": self.use_web},
        )

    def generate(self, request: AIRequest) -> AIResponse:
        self.synthesis_requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "moderate",
                "confidence": 0.82,
                "rationale": "The supplied evidence and available external context support moderate concern.",
                "database_evidence_refs": ["R001", "C001"],
                "external_source_refs": ["W001"] if self.use_web else [],
                "considerations": [
                    {
                        "finding": "Current tooling remains available.",
                        "basis": "mixed" if self.use_web else "registry_evidence",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["R001"],
                        "external_source_refs": ["W001"] if self.use_web else [],
                    }
                ],
                "config_rules_considered": ["most_specific_available"],
                "governed_baseline_relation": "higher_concern",
                "uncertainty": "The AI result is advisory to the consumer.",
            },
            usage=AIUsage(input_tokens=200, output_tokens=100, total_tokens=300),
        )


def test_capability_synthesis_keeps_registry_and_baseline_context_but_model_may_differ():
    policy = load_synthesis_policy()
    provider = _FakeCapabilityProvider(use_web=True)
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

    assert provider.research_prompts
    assert "NF00369" in provider.research_prompts[0]
    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "moderate"
    assert overall["governed_baseline"]["semantic_level"] == "low"
    assert overall["capabilities_available"]["web_search"] is True
    assert overall["capabilities_used"]["web_search"] is True
    assert overall["external_source_refs"] == ["W001"]
    assert result["mode"] == "capability_driven_ai_synthesis"


def test_historical_web_research_enabled_switch_no_longer_controls_capability_availability():
    old_disabled = _azure_config(web_research={"enabled": False})
    old_enabled = _azure_config(web_research={"enabled": True})

    assert old_disabled.web_research_enabled is True
    assert old_enabled.web_research_enabled is True
