from __future__ import annotations

from types import SimpleNamespace

from preservation_risk_manager.ai import (
    AIMessage,
    AIProviderConfig,
    AIRequest,
    AIToolDefinition,
    build_ai_provider,
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


def test_required_tool_name_is_sent_as_tool_choice():
    tool_call = SimpleNamespace(
        id="call_status",
        function=SimpleNamespace(
            name="report_provider_status",
            arguments='{"status":"available","message":"ok"}',
        ),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[tool_call]),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="test-deployment",
    )
    client = FakeClient(response)
    config = AIProviderConfig.from_dict({
        "provider": "azure_openai",
        "endpoint": "https://example.openai.azure.com/",
        "api_key": "test-key",
        "api_version": "2024-10-21",
        "deployment": "test-deployment",
    })
    provider = build_ai_provider(config, client=client)
    tool = AIToolDefinition(
        name="report_provider_status",
        description="Report provider status.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["available"]},
                "message": {"type": "string"},
            },
            "required": ["status", "message"],
            "additionalProperties": False,
        },
    )

    result = provider.generate(AIRequest(
        messages=(AIMessage("user", "Use the status tool."),),
        tools=(tool,),
        required_tool_name=tool.name,
    ))

    assert result.tool_calls[0].name == tool.name
    assert client.completions.last_payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "report_provider_status"},
    }
