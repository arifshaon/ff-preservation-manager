from __future__ import annotations

import json

from preservation_risk_manager.ai.base import (
    AIMessage,
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
)
from preservation_risk_manager.ai.config import AIProviderConfig
from preservation_risk_manager.ai.factory import build_ai_provider
from preservation_risk_manager.ai.request_logging import AIRequestLoggingProvider, with_ai_request_logging


class _FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True, web_search=True)

    @property
    def model_name(self) -> str:
        return "fake-model"

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(provider=self.provider_name, model=self.model_name, text="ok")

    def generate_with_capabilities(self, request: AIRequest, *, allowed_domains=(), blocked_domains=()) -> AIResponse:
        return AIResponse(provider=self.provider_name, model=self.model_name, text="ok")


def test_input_log_file_is_optional_config():
    disabled = AIProviderConfig.from_dict({"provider": "azure_openai"})
    enabled = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "input_log_file": "logs/ai-inputs.jsonl",
    })

    assert disabled.input_log_file is None
    assert enabled.input_log_file == "logs/ai-inputs.jsonl"
    assert enabled.redacted()["input_log_file"] == "logs/ai-inputs.jsonl"


def test_logging_provider_appends_exact_ai_request(tmp_path):
    log_path = tmp_path / "nested" / "ai-inputs.jsonl"
    provider = AIRequestLoggingProvider(_FakeProvider(), log_path)
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    request = AIRequest(
        messages=(
            AIMessage("system", "SYSTEM MESSAGE"),
            AIMessage("user", "USER MESSAGE WITH FULL EVIDENCE"),
        ),
        response_schema=schema,
        response_schema_name="test_schema",
        temperature=0.0,
        max_output_tokens=2000,
    )

    provider.generate_with_capabilities(
        request,
        allowed_domains=("example.org",),
        blocked_domains=("blocked.example",),
    )

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["sequence"] == 1
    assert row["call_type"] == "generate_with_capabilities"
    assert row["provider"] == "fake"
    assert row["model"] == "fake-model"
    assert row["request"]["messages"] == [
        {"role": "system", "content": "SYSTEM MESSAGE"},
        {"role": "user", "content": "USER MESSAGE WITH FULL EVIDENCE"},
    ]
    assert row["request"]["response_schema"] == schema
    assert row["request"]["response_schema_name"] == "test_schema"
    assert row["request"]["max_output_tokens"] == 2000
    assert row["capability_options"] == {
        "web_search": True,
        "allowed_domains": ["example.org"],
        "blocked_domains": ["blocked.example"],
        "tool_choice": "auto",
    }


def test_logging_is_not_enabled_without_path():
    provider = _FakeProvider()
    assert with_ai_request_logging(provider, None) is provider
    assert with_ai_request_logging(provider, "") is provider


def test_factory_wraps_provider_when_input_log_file_is_configured(tmp_path):
    log_path = tmp_path / "factory-ai-inputs.jsonl"
    config = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example-resource.openai.azure.com/",
        "deployment": "test-deployment",
        "input_log_file": str(log_path),
    })

    provider = build_ai_provider(config, client=object())

    assert isinstance(provider, AIRequestLoggingProvider)
    assert provider.delegate.provider_name == "azure_openai"
    assert provider.log_path == log_path
    assert log_path.exists()
