from __future__ import annotations

from typing import Any

from preservation_risk_manager.ai.base import (
    AIConfigurationError,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
)
from preservation_risk_manager.ai.providers.azure_openai import AzureOpenAIProvider


class OpenAICompatibleProvider(AzureOpenAIProvider):
    """Provider for OpenAI-compatible hosted or local HTTP endpoints.

    This is intentionally separate from Azure OpenAI configuration. It provides
    the extension point for OpenAI's public API and compatible endpoints such as
    Gemini's OpenAI compatibility layer, Claude's evaluation compatibility layer,
    vLLM, llama.cpp, or Ollama gateways.

    Provider-hosted web search is deliberately not advertised here. The generic
    compatibility contract uses Chat Completions for one-call structured synthesis;
    provider-specific Responses/search tooling requires a dedicated provider adapter.
    """

    provider_name = "openai_compatible"
    capabilities = AIProviderCapabilities(
        structured_output=True,
        tool_calling=True,
        streaming=False,
        web_search=False,
    )

    @property
    def model_name(self) -> str:
        assert self.config.model is not None
        return self.config.model

    def _validate_config(self) -> None:
        if not self.config.endpoint:
            raise AIConfigurationError("OpenAI-compatible provider requires 'endpoint'.")
        if not self.config.model:
            raise AIConfigurationError("OpenAI-compatible provider requires 'model'.")

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError(
                "OpenAI-compatible support requires the optional AI dependency. "
                "Install with: python -m pip install -e '.[ai]'"
            ) from exc
        return OpenAI(
            base_url=self.config.endpoint,
            api_key=self.config.resolve_api_key(required=False) or "local-no-key",
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
        )

    def generate_with_capabilities(
        self,
        request: AIRequest,
        *,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
    ) -> AIResponse:
        """Run compatibility synthesis as one Chat Completions request.

        The generic OpenAI-compatible contract cannot safely assume that a vendor
        implements OpenAI/Azure Responses web-search semantics. The synthesis prompt
        still receives the full registry/methodology context, but no hosted search
        tool is injected. A native provider adapter may opt into richer capabilities.
        """
        return self.generate(request)
