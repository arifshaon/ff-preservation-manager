from __future__ import annotations

from typing import Any

from preservation_risk_manager.ai.base import AIConfigurationError
from preservation_risk_manager.ai.providers.azure_openai import AzureOpenAIProvider


class OpenAICompatibleProvider(AzureOpenAIProvider):
    """Provider for OpenAI-compatible hosted or local HTTP endpoints.

    This is intentionally separate from Azure OpenAI configuration. It provides
    the extension point for OpenAI's public API and local servers such as vLLM,
    llama.cpp, or Ollama when they expose a compatible endpoint.
    """

    provider_name = "openai_compatible"

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
        )
