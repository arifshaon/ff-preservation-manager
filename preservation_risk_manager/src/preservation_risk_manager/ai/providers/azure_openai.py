from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.ai.base import (
    AIConfigurationError,
    AIProvider,
    AIProviderCapabilities,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIToolCall,
    AIUsage,
    parse_json_object,
)
from preservation_risk_manager.ai.config import AIProviderConfig


class AzureOpenAIProvider(AIProvider):
    """Azure OpenAI implementation of the provider-neutral AI interface."""

    provider_name = "azure_openai"
    capabilities = AIProviderCapabilities(
        structured_output=True,
        tool_calling=True,
        streaming=False,
    )

    def __init__(self, config: AIProviderConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._validate_config()
        self._client = client if client is not None else self._build_client()

    @property
    def model_name(self) -> str:
        assert self.config.deployment is not None
        return self.config.deployment

    def _validate_config(self) -> None:
        if not self.config.endpoint:
            raise AIConfigurationError("Azure OpenAI provider requires 'endpoint'.")
        if not self.config.deployment:
            raise AIConfigurationError(
                "Azure OpenAI provider requires 'deployment' (the Azure model deployment name)."
            )

    def _build_client(self) -> Any:
        try:
            from openai import AzureOpenAI
        except ImportError as exc:
            raise AIConfigurationError(
                "Azure OpenAI support requires the optional AI dependency. "
                "Install with: python -m pip install -e '.[ai]'"
            ) from exc
        return AzureOpenAI(
            azure_endpoint=self.config.endpoint,
            api_key=self.config.resolve_api_key(required=True),
            api_version=self.config.api_version or "2024-10-21",
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [message.to_dict() for message in request.messages],
        }
        temperature = (
            request.temperature
            if request.temperature is not None
            else self.config.temperature
        )
        payload["temperature"] = temperature

        max_output_tokens = request.max_output_tokens or self.config.max_output_tokens
        if max_output_tokens is not None:
            payload["max_completion_tokens"] = max_output_tokens

        if request.tools:
            payload["tools"] = [tool.to_openai_tool() for tool in request.tools]
            payload["parallel_tool_calls"] = False
            if request.required_tool_name:
                payload["tool_choice"] = {
                    "type": "function",
                    "function": {"name": request.required_tool_name},
                }

        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema_name,
                    "strict": True,
                    "schema": request.response_schema,
                },
            }

        try:
            completion = self._client.chat.completions.create(**payload)
        except Exception as exc:  # provider SDK exceptions vary by version
            raise AIProviderError(f"Azure OpenAI request failed: {exc}") from exc

        try:
            choice = completion.choices[0]
            message = choice.message
        except (AttributeError, IndexError, TypeError) as exc:
            raise AIProviderError("Azure OpenAI returned an unexpected response shape.") from exc

        text = getattr(message, "content", None)
        structured = None
        if request.response_schema is not None and text:
            structured = parse_json_object(text, label="Azure OpenAI structured response")

        tool_calls: list[AIToolCall] = []
        for call in getattr(message, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            if function is None:
                continue
            arguments_text = getattr(function, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(arguments_text)
            except json.JSONDecodeError as exc:
                raise AIProviderError(
                    f"Azure OpenAI tool call '{getattr(function, 'name', '')}' returned invalid JSON arguments."
                ) from exc
            if not isinstance(arguments, dict):
                raise AIProviderError("AI tool-call arguments must be a JSON object.")
            tool_calls.append(
                AIToolCall(
                    call_id=str(getattr(call, "id", "")),
                    name=str(getattr(function, "name", "")),
                    arguments=arguments,
                )
            )

        usage_obj = getattr(completion, "usage", None)
        usage = AIUsage(
            input_tokens=getattr(usage_obj, "prompt_tokens", None),
            output_tokens=getattr(usage_obj, "completion_tokens", None),
            total_tokens=getattr(usage_obj, "total_tokens", None),
        )
        response_model = str(getattr(completion, "model", None) or self.model_name)
        return AIResponse(
            provider=self.provider_name,
            model=response_model,
            text=text,
            structured=structured,
            tool_calls=tuple(tool_calls),
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage,
            metadata={"deployment": self.model_name},
        )
