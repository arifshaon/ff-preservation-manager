import pytest

from preservation_risk_manager.ai.base import AIConfigurationError
from preservation_risk_manager.ai.config import AIProviderConfig


def test_ai_provider_retries_default_to_zero():
    config = AIProviderConfig.from_dict({"provider": "azure_openai"})
    assert config.max_retries == 0


def test_ai_provider_retry_count_is_configurable():
    config = AIProviderConfig.from_dict({"provider": "azure_openai", "max_retries": 2})
    assert config.max_retries == 2
    assert config.redacted()["max_retries"] == 2


def test_ai_provider_retry_count_cannot_be_negative():
    with pytest.raises(AIConfigurationError, match="max_retries"):
        AIProviderConfig.from_dict({"provider": "azure_openai", "max_retries": -1})
