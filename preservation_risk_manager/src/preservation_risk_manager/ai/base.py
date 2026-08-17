from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Any


class AIError(RuntimeError):
    """Base error for AI provider/configuration failures."""


class AIConfigurationError(AIError):
    """Raised when an AI provider configuration is invalid."""


class AIProviderError(AIError):
    """Raised when an AI provider cannot complete a request."""


@dataclass(frozen=True)
class AIToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.call_id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, separators=(",", ":"), sort_keys=True),
            },
        }


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[AIToolCall, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported AI message role: {self.role}")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("Tool messages require tool_call_id.")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistant messages may contain tool_calls.")
        if self.content is None and not (self.role == "assistant" and self.tool_calls):
            raise ValueError("Message content may be null only for an assistant tool-call message.")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            data["name"] = self.name
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            data["tool_calls"] = [call.to_openai_tool_call() for call in self.tool_calls]
        return data


@dataclass(frozen=True)
class AIToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = True

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
                "strict": self.strict,
            },
        }


@dataclass(frozen=True)
class AIRequest:
    messages: tuple[AIMessage, ...]
    tools: tuple[AIToolDefinition, ...] = ()
    required_tool_name: str | None = None
    response_schema: dict[str, Any] | None = None
    response_schema_name: str = "assistant_response"
    temperature: float | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("AIRequest requires at least one message.")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if self.required_tool_name:
            tool_names = {tool.name for tool in self.tools}
            if self.required_tool_name not in tool_names:
                raise ValueError(
                    f"required_tool_name '{self.required_tool_name}' is not present in request tools."
                )


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class AIResponse:
    provider: str
    model: str
    text: str | None = None
    structured: dict[str, Any] | None = None
    tool_calls: tuple[AIToolCall, ...] = ()
    finish_reason: str | None = None
    usage: AIUsage = field(default_factory=AIUsage)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_assistant_message(self) -> AIMessage:
        return AIMessage(
            role="assistant",
            content=self.text,
            tool_calls=self.tool_calls,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "structured": self.structured,
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in self.tool_calls
            ],
            "finish_reason": self.finish_reason,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AIProviderCapabilities:
    structured_output: bool = False
    tool_calling: bool = False
    streaming: bool = False


class AIProvider(ABC):
    provider_name = "unknown"
    capabilities = AIProviderCapabilities()

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the provider model/deployment identifier used for requests."""

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """Generate one response from the configured provider."""

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "capabilities": {
                "structured_output": self.capabilities.structured_output,
                "tool_calling": self.capabilities.tool_calling,
                "streaming": self.capabilities.streaming,
            },
        }


def parse_json_object(value: str, *, label: str = "AI response") -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"{label} was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AIProviderError(f"{label} must be a JSON object.")
    return parsed
