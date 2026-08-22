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
from preservation_risk_manager.ai.research_synthesis import synthesize_with_web_research
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _FakeResponsesAPI:
    def __init__(self):
        self.payload = None

    def create(self, **payload):
        self.payload = payload
        return SimpleNamespace(
            model="test-deployment",
            output_text="Official documentation confirms current reader support and supplements the stored preservation evidence.",
            output=[
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
            ],
            usage=SimpleNamespace(input_tokens=50, output_tokens=30, total_tokens=80),
        )


class _FakeResponsesClient:
    def __init__(self):
        self.responses = _FakeResponsesAPI()


def test_azure_provider_web_research_uses_responses_web_search_and_preserves_citations():
    config = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "api_key": "test-key",
        "deployment": "test-deployment",
        "web_research": {
            "enabled": True,
            "allowed_domains": ["example.org"],
        },
    })
    responses_client = _FakeResponsesClient()
    provider = AzureOpenAIProvider(config, client=object(), responses_client=responses_client)

    result = provider.research_web("Verify the stored PDF evidence.")

    assert result.text.startswith("Official documentation")
    assert result.search_queries == ("PDF 1.7 official current reader support specification",)
    assert result.citations[0].url == "https://example.org/spec"
    assert result.citations[0].title == "Official specification"
    payload = responses_client.responses.payload
    assert payload["tools"][0]["type"] == "web_search"
    assert payload["tools"][0]["filters"]["allowed_domains"] == ["example.org"]
    assert "web_search_call.action.sources" in payload["include"]


class _FakeResearchProvider(AIProvider):
    provider_name = "fake_research"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    def __init__(self):
        self.research_prompts: list[str] = []
        self.synthesis_requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-research-model"

    def research_web(self, prompt: str, *, allowed_domains=(), blocked_domains=()):
        self.research_prompts.append(prompt)
        return AIWebResearchResponse(
            provider=self.provider_name,
            model=self.model_name,
            text=(
                "Current authoritative documentation confirms the stored exact-format identification and adds "
                "current evidence about active tooling. A newer authoritative preservation note also qualifies "
                "the older low-concern assessment because some advanced features remain harder to preserve."
            ),
            citations=(
                AIWebCitation("https://example.org/current-tooling", "Current tooling"),
                AIWebCitation("https://example.org/preservation-note", "Preservation note"),
            ),
            search_queries=("verify PDF 1.7 current preservation tooling",),
            consulted_urls=(
                "https://example.org/current-tooling",
                "https://example.org/preservation-note",
            ),
            usage=AIUsage(input_tokens=100, output_tokens=80, total_tokens=180),
        )

    def generate(self, request: AIRequest) -> AIResponse:
        self.synthesis_requests.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "semantic_level": "moderate",
                "confidence": 0.82,
                "rationale": (
                    "The registry remains the primary evidence base. Current cited web evidence confirms much of it "
                    "but qualifies the governed Low baseline with additional current preservation concerns."
                ),
                "database_evidence_refs": ["R001", "C001"],
                "web_source_refs": ["W001", "W002"],
                "verification_findings": [
                    {
                        "finding": "Current tooling support remains active.",
                        "relationship_to_database": "supplements",
                        "risk_effect": "reduces_concern",
                        "database_evidence_refs": ["R001"],
                        "web_source_refs": ["W001"],
                        "rationale": "The current tool documentation adds up-to-date support evidence.",
                    },
                    {
                        "finding": "Some advanced features remain harder to preserve reliably.",
                        "relationship_to_database": "qualifies_or_updates",
                        "risk_effect": "raises_concern",
                        "database_evidence_refs": ["R001"],
                        "web_source_refs": ["W002"],
                        "rationale": "The current preservation note qualifies the older low-concern baseline.",
                    },
                ],
                "policy_rules_applied": [
                    "configured_source_mappings_are_binding",
                    "missing_assessment_policy=exclude",
                    "numeric_aggregation=forbidden_across_source_scales",
                ],
                "governed_baseline_relation": "higher_concern",
                "uncertainty": "The researched finding is current but does not replace the stored NARA assessment.",
            },
            usage=AIUsage(input_tokens=200, output_tokens=100, total_tokens=300),
        )


def test_web_researched_synthesis_starts_from_registry_and_preserves_governed_baseline():
    policy = load_synthesis_policy()
    provider = _FakeResearchProvider()
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "method": "config_driven_scope_aware_synthesis",
    }

    result = synthesize_with_web_research(
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
    research_prompt = provider.research_prompts[0]
    assert "VERIFY AND SUPPLEMENT" in research_prompt
    assert "Do not search for a generic overall 'risk score'" in research_prompt
    assert "NF00369" in research_prompt

    overall = result["overall_synthesized_risk"]
    assert overall["semantic_level"] == "moderate"
    assert overall["web_researched"] is True
    assert overall["governed_baseline"]["semantic_level"] == "low"
    assert overall["governed_baseline_relation"] == "higher_concern"
    assert overall["database_evidence_refs"] == ["R001", "C001"]
    assert overall["web_source_refs"] == ["W001", "W002"]
    assert result["web_research"]["citations"][0]["url"] == "https://example.org/current-tooling"
    assert result["web_research"]["persisted"] is False

    synthesis_prompt = provider.synthesis_requests[0].messages[-1].content or ""
    assert "registry evidence as the primary evidence base" in synthesis_prompt
    assert "generic_independent_risk_analysis_forbidden" in synthesis_prompt


def test_web_research_config_is_explicit_opt_in():
    disabled = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "api_key": "test-key",
        "deployment": "test-deployment",
    })
    enabled = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "api_key": "test-key",
        "deployment": "test-deployment",
        "web_research": {
            "enabled": True,
            "allowed_domains": ["loc.gov", "archives.gov"],
            "blocked_domains": ["reddit.com"],
        },
    })

    assert disabled.web_research_enabled is False
    assert enabled.web_research_enabled is True
    assert enabled.web_research_allowed_domains == ("loc.gov", "archives.gov")
    assert enabled.web_research_blocked_domains == ("reddit.com",)
