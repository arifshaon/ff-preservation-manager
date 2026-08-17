from __future__ import annotations

from typing import Any

from preservation_risk_manager.ai.base import AIConfigurationError, AIProvider
from preservation_risk_manager.ai.config import AIProviderConfig
from preservation_risk_manager.ai.providers.azure_openai import AzureOpenAIProvider
from preservation_risk_manager.ai.providers.openai_compatible import OpenAICompatibleProvider


_PROVIDER_ALIASES = {
    "azure": "azure_openai",
    "azure_openai": "azure_openai",
    "openai-compatible": "openai_compatible",
    "openai_compatible": "openai_compatible",
    "openai": "openai_compatible",
    "local": "openai_compatible",
}


def build_ai_provider(
    config: AIProviderConfig,
    *,
    client: Any | None = None,
) -> AIProvider:
    provider_name = _PROVIDER_ALIASES.get(config.provider, config.provider)
    if provider_name == "azure_openai":
        return AzureOpenAIProvider(config, client=client)
    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider(config, client=client)
    raise AIConfigurationError(
        f"Unsupported AI provider '{config.provider}'. "
        "Supported providers: azure_openai, openai_compatible."
    )
