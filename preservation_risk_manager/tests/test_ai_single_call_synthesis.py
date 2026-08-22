from __future__ import annotations

import json
from types import SimpleNamespace

from preservation_risk_manager.ai import synthesize_with_capabilities
from preservation_risk_manager.ai.config import AIProviderConfig
from preservation_risk_manager.ai.providers.azure_openai import AzureOpenAIProvider
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


class _FailChatCompletions:
    class _Completions:
        def create(self, **kwargs):
            raise AssertionError("Chat Completions must not be called for capability-driven overall synthesis")

    def __init__(self):
        self.completions = self._Completions()


class _FailChatClient:
    def __init__(self):
        self.chat = _FailChatCompletions()


class _ResponsesAPI:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **payload):
        self.calls.append(payload)
        output = {
            "semantic_level": "low",
            "confidence": 0.88,
            "rationale": "The supplied exact-format assessment and current external information support Low concern.",
            "database_evidence_refs": ["R001"],
            "considerations": [
                {
                    "finding": "The exact-format governed source assessment is Low concern.",
                    "basis": "registry_evidence",
                    "risk_effect": "reduces_concern",
                    "database_evidence_refs": ["R001"],
                },
                {
                    "finding": "Current authoritative documentation remains available.",
                    "basis": "external_information",
                    "risk_effect": "reduces_concern",
                    "database_evidence_refs": [],
                },
            ],
            "config_rules_considered": ["most_specific_available"],
            "governed_baseline_relation": "same",
            "uncertainty": "Some PDF feature-level risks remain content dependent.",
        }
        return SimpleNamespace(
            model="test-deployment",
            status="completed",
            output_text=json.dumps(output),
            output=[
                {
                    "type": "web_search_call",
                    "action": {
                        "query": "PDF 1.7 current specification preservation support",
                        "sources": [{"url": "https://example.org/pdf17"}],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.org/pdf17",
                                    "title": "PDF 1.7 documentation",
                                }
                            ]
                        }
                    ],
                },
            ],
            usage=SimpleNamespace(input_tokens=200, output_tokens=80, total_tokens=280),
        )


class _ResponsesClient:
    def __init__(self):
        self.responses = _ResponsesAPI()


def test_azure_capability_synthesis_uses_one_responses_call_with_optional_web_search():
    config = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "api_key": "test-key",
        "deployment": "test-deployment",
        "external_research": {"allowed_domains": ["example.org"]},
    })
    responses_client = _ResponsesClient()
    provider = AzureOpenAIProvider(
        config,
        client=_FailChatClient(),
        responses_client=responses_client,
    )
    policy = load_synthesis_policy()

    result = synthesize_with_capabilities(
        provider,
        format_context={"canonical_id": "puid-fmt-276", "label": "PDF 1.7", "puids": ["fmt/276"]},
        policy=policy,
        governed_synthesis={
            "assessed": True,
            "semantic_level": "low",
            "semantic_label": "Low concern",
            "method": "config_driven_scope_aware_synthesis",
        },
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

    assert len(responses_client.responses.calls) == 1
    payload = responses_client.responses.calls[0]
    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["type"] == "web_search"
    assert payload["tools"][0]["filters"]["allowed_domains"] == ["example.org"]
    assert payload["text"]["verbosity"] == "low"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True

    assert result["status"] == "ok"
    assert result["overall_synthesized_risk"]["semantic_level"] == "low"
    assert result["overall_synthesized_risk"]["governed_baseline"]["semantic_level"] == "low"
    assert result["overall_synthesized_risk"]["capabilities_used"]["web_search"] is True
    assert result["external_capability"]["web_search_used"] is True
    assert result["external_capability"]["sources"][0]["url"] == "https://example.org/pdf17"
    assert result["usage"]["total_tokens"] == 280
