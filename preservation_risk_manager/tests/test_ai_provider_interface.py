from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from preservation_risk_manager.ai import (
    AIConfigurationError,
    AIMessage,
    AIProviderConfig,
    AIRequest,
    AIToolDefinition,
    build_ai_provider,
    load_ai_config,
)


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.last_payload = None

    def create(self, **kwargs):
        self.last_payload = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.completions = FakeCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


def _completion(*, content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls or []),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="test-deployment",
    )


def _azure_config(**overrides):
    data = {
        "provider": "azure_openai",
        "endpoint": "https://example.openai.azure.com/",
        "api_key": "test-key",
        "api_version": "2024-10-21",
        "deployment": "test-deployment",
    }
    data.update(overrides)
    return AIProviderConfig.from_dict(data)


def test_load_ai_config_accepts_top_level_ai_block_and_redacts_key(tmp_path: Path):
    path = tmp_path / "ai.json"
    path.write_text(json.dumps({"ai": {
        "provider": "azure_openai",
        "endpoint": "https://example.openai.azure.com/",
        "api_key": "secret-value",
        "deployment": "risk-model",
    }}), encoding="utf-8")

    config = load_ai_config(path)

    assert config.provider == "azure_openai"
    assert config.deployment == "risk-model"
    assert config.redacted()["api_key"] == "***"
    assert "secret-value" not in json.dumps(config.redacted())


def test_placeholder_key_is_not_accepted_as_a_real_secret():
    config = _azure_config(api_key="<QNL_AZURE_OPENAI_API_KEY>")
    with pytest.raises(AIConfigurationError, match="placeholder"):
        config.resolve_api_key()


def test_azure_provider_builds_strict_structured_output_request():
    response = _completion(content='{"answer_id":"unknown","rationale":"Insufficient evidence"}')
    client = FakeClient(response)
    provider = build_ai_provider(_azure_config(), client=client)
    schema = {
        "type": "object",
        "properties": {
            "answer_id": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["answer_id", "rationale"],
        "additionalProperties": False,
    }

    result = provider.generate(AIRequest(
        messages=(AIMessage("user", "Assess the supplied evidence."),),
        response_schema=schema,
        response_schema_name="risk_answer",
    ))

    assert result.provider == "azure_openai"
    assert result.structured == {
        "answer_id": "unknown",
        "rationale": "Insufficient evidence",
    }
    payload = client.completions.last_payload
    assert payload["model"] == "test-deployment"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] == schema


def test_azure_provider_parses_tool_calls():
    tool_call = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(
            name="assess_format",
            arguments='{"format_query":"fmt/18"}',
        ),
    )
    client = FakeClient(_completion(tool_calls=[tool_call]))
    provider = build_ai_provider(_azure_config(), client=client)
    tool = AIToolDefinition(
        name="assess_format",
        description="Assess one format.",
        input_schema={
            "type": "object",
            "properties": {"format_query": {"type": "string"}},
            "required": ["format_query"],
            "additionalProperties": False,
        },
    )

    result = provider.generate(AIRequest(
        messages=(AIMessage("user", "What is the risk of PDF 1.4?"),),
        tools=(tool,),
    ))

    assert result.tool_calls[0].name == "assess_format"
    assert result.tool_calls[0].arguments == {"format_query": "fmt/18"}
    payload = client.completions.last_payload
    assert payload["tools"][0]["function"]["strict"] is True
    assert payload["parallel_tool_calls"] is False


def test_openai_compatible_provider_uses_same_contract_with_injected_client():
    config = AIProviderConfig.from_dict({
        "provider": "local",
        "endpoint": "http://127.0.0.1:8000/v1",
        "model": "local-risk-model",
    })
    client = FakeClient(_completion(content="Local response"))
    provider = build_ai_provider(config, client=client)

    result = provider.generate(AIRequest(
        messages=(AIMessage("user", "Hello"),),
    ))

    assert provider.provider_name == "openai_compatible"
    assert provider.model_name == "local-risk-model"
    assert result.text == "Local response"
    assert client.completions.last_payload["model"] == "local-risk-model"


def test_ai_info_cli_does_not_expose_placeholder_key(tmp_path: Path, capsys):
    from preservation_risk_manager.ai.cli import main

    path = tmp_path / "ai.json"
    path.write_text(json.dumps({"ai": {
        "provider": "azure_openai",
        "endpoint": "https://qnl-openai-qadc-prod-001.openai.azure.com/",
        "api_key": "<QNL_AZURE_OPENAI_API_KEY>",
        "deployment": "<AZURE_OPENAI_DEPLOYMENT_NAME>",
    }}), encoding="utf-8")

    assert main(["info", "--config", str(path)]) == 0
    output = capsys.readouterr().out
    assert "<QNL_AZURE_OPENAI_API_KEY>" not in output
    assert '"api_key": "***"' in output
