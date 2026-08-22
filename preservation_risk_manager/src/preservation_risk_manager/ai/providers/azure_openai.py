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
    AIWebCitation,
    AIWebResearchResponse,
    parse_json_object,
)
from preservation_risk_manager.ai.config import AIProviderConfig


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class AzureOpenAIProvider(AIProvider):
    """Azure OpenAI implementation of the provider-neutral AI interface."""

    provider_name = "azure_openai"
    capabilities = AIProviderCapabilities(
        structured_output=True,
        tool_calling=True,
        streaming=False,
        web_search=True,
    )

    def __init__(self, config: AIProviderConfig, *, client: Any | None = None, responses_client: Any | None = None) -> None:
        self.config = config
        self._validate_config()
        self._client = client if client is not None else self._build_client()
        self._responses_client = responses_client

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

    def _responses_base_url(self) -> str:
        assert self.config.endpoint is not None
        endpoint = self.config.endpoint.rstrip("/")
        if endpoint.endswith("/openai/v1"):
            return endpoint + "/"
        return endpoint + "/openai/v1/"

    def _get_responses_client(self) -> Any:
        if self._responses_client is not None:
            return self._responses_client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError(
                "Azure external research requires a Responses-capable OpenAI Python SDK. "
                "Install or upgrade with: python -m pip install -U openai"
            ) from exc
        self._responses_client = OpenAI(
            base_url=self._responses_base_url(),
            api_key=self.config.resolve_api_key(required=True),
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
        )
        if not hasattr(self._responses_client, "responses"):
            raise AIConfigurationError(
                "The installed OpenAI Python SDK does not expose the Responses API required for external research. "
                "Upgrade it with: python -m pip install -U openai"
            )
        return self._responses_client

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

    def research_web(
        self,
        prompt: str,
        *,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
    ) -> AIWebResearchResponse:
        """Expose Azure Responses web_search with tool_choice=auto.

        The application makes the capability available; the model decides whether
        to call it. A valid ungrounded response is therefore not an error.
        """
        client = self._get_responses_client()
        tool: dict[str, Any] = {"type": "web_search"}
        effective_allowed = tuple(allowed_domains) or self.config.external_research_allowed_domains
        effective_blocked = tuple(blocked_domains) or self.config.external_research_blocked_domains
        filters: dict[str, Any] = {}
        if effective_allowed:
            filters["allowed_domains"] = list(effective_allowed)
        if effective_blocked:
            filters["blocked_domains"] = list(effective_blocked)
        if filters:
            tool["filters"] = filters

        payload: dict[str, Any] = {
            "model": self.model_name,
            "tools": [tool],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
            "input": prompt,
        }
        try:
            response = client.responses.create(**payload)
        except Exception as exc:
            raise AIProviderError(f"Azure OpenAI external-research request failed: {exc}") from exc

        text = str(_value(response, "output_text", "") or "").strip()
        outputs = _value(response, "output", ()) or ()
        citations: list[AIWebCitation] = []
        citation_seen: set[tuple[str, str | None]] = set()
        queries: list[str] = []
        consulted_urls: list[str] = []
        web_search_used = False

        for output in outputs:
            output_type = str(_value(output, "type", "") or "")
            if output_type == "web_search_call":
                web_search_used = True
                action = _value(output, "action", None)
                query = str(_value(action, "query", "") or "").strip()
                if query and query not in queries:
                    queries.append(query)
                for source in _value(action, "sources", ()) or ():
                    url = str(_value(source, "url", "") or "").strip()
                    if url and url not in consulted_urls:
                        consulted_urls.append(url)
            if output_type != "message":
                continue
            for content in _value(output, "content", ()) or ():
                for annotation in _value(content, "annotations", ()) or ():
                    if str(_value(annotation, "type", "") or "") != "url_citation":
                        continue
                    url = str(_value(annotation, "url", "") or "").strip()
                    title_raw = _value(annotation, "title", None)
                    title = str(title_raw).strip() if title_raw is not None else None
                    if not url:
                        continue
                    key = (url, title)
                    if key in citation_seen:
                        continue
                    citation_seen.add(key)
                    citations.append(AIWebCitation(url=url, title=title))
                    if url not in consulted_urls:
                        consulted_urls.append(url)

        if not text:
            raise AIProviderError("Azure OpenAI capability-assisted analysis returned no text.")

        usage_obj = _value(response, "usage", None)
        usage = AIUsage(
            input_tokens=_value(usage_obj, "input_tokens", None),
            output_tokens=_value(usage_obj, "output_tokens", None),
            total_tokens=_value(usage_obj, "total_tokens", None),
        )
        response_model = str(_value(response, "model", None) or self.model_name)
        return AIWebResearchResponse(
            provider=self.provider_name,
            model=response_model,
            text=text,
            citations=tuple(citations),
            search_queries=tuple(queries),
            consulted_urls=tuple(consulted_urls),
            usage=usage,
            metadata={
                "deployment": self.model_name,
                "web_search_available": True,
                "web_search_used": web_search_used,
                "external_capability": "azure_openai_responses_web_search",
            },
        )
