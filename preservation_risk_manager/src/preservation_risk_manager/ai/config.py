from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai.base import AIConfigurationError


_PLACEHOLDER_MARKERS = (
    "<paste_",
    "<replace_",
    "<azure_",
    "<qnl_",
    "replace_me",
    "changeme",
)


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        raise AIConfigurationError("AI web-search domain filters must be strings or arrays of strings.")
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str
    endpoint: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 0
    human_format_assessment_limit: int = 10
    web_research_enabled: bool = False
    web_research_allowed_domains: tuple[str, ...] = ()
    web_research_blocked_domains: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIProviderConfig":
        provider = str(data.get("provider") or "").strip().lower()
        if not provider:
            raise AIConfigurationError("AI configuration requires 'provider'.")
        max_retries = int(data.get("max_retries", 0))
        if max_retries < 0:
            raise AIConfigurationError("AI configuration 'max_retries' must be zero or greater.")

        # ``human_ai_format_limit`` was the first name introduced for this
        # setting. Preserve it as a compatibility alias, but the setting now
        # caps total human-query assessments (deterministic + optional AI), not
        # merely the subset sent to AI.
        raw_human_limit = data.get(
            "human_format_assessment_limit",
            data.get("human_ai_format_limit", 10),
        )
        human_format_assessment_limit = int(raw_human_limit)
        if human_format_assessment_limit <= 0:
            raise AIConfigurationError(
                "AI configuration 'human_format_assessment_limit' must be greater than zero."
            )

        web_research = data.get("web_research") or {}
        if not isinstance(web_research, dict):
            raise AIConfigurationError("AI configuration 'web_research' must be an object.")
        allowed_domains = _string_tuple(web_research.get("allowed_domains"))
        blocked_domains = _string_tuple(web_research.get("blocked_domains"))
        if len(allowed_domains) > 100:
            raise AIConfigurationError("AI web research supports at most 100 allowed domains.")

        return cls(
            provider=provider,
            endpoint=_optional_string(data.get("endpoint")),
            api_key=_optional_string(data.get("api_key")),
            api_key_env=_optional_string(data.get("api_key_env")),
            api_version=_optional_string(data.get("api_version")),
            deployment=_optional_string(data.get("deployment")),
            model=_optional_string(data.get("model")),
            temperature=float(data.get("temperature", 0.0)),
            max_output_tokens=(
                int(data["max_output_tokens"])
                if data.get("max_output_tokens") is not None
                else None
            ),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            max_retries=max_retries,
            human_format_assessment_limit=human_format_assessment_limit,
            web_research_enabled=bool(web_research.get("enabled", False)),
            web_research_allowed_domains=allowed_domains,
            web_research_blocked_domains=blocked_domains,
        )

    @property
    def human_ai_format_limit(self) -> int:
        """Backward-compatible alias for the former setting name."""
        return self.human_format_assessment_limit

    def resolve_api_key(self, *, required: bool = True) -> str | None:
        if self.api_key_env:
            value = os.getenv(self.api_key_env)
            if value:
                return value
            if required:
                raise AIConfigurationError(
                    f"Environment variable '{self.api_key_env}' is not set for the AI provider API key."
                )
            return None
        if self.api_key and not _looks_like_placeholder(self.api_key):
            return self.api_key
        if required:
            raise AIConfigurationError(
                "AI provider API key is missing or still contains the example placeholder."
            )
        return None

    @property
    def configured_model(self) -> str | None:
        return self.deployment or self.model

    def redacted(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "api_key": "***" if self.api_key else None,
            "api_key_env": self.api_key_env,
            "api_version": self.api_version,
            "deployment": self.deployment,
            "model": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "human_format_assessment_limit": self.human_format_assessment_limit,
            "web_research": {
                "enabled": self.web_research_enabled,
                "allowed_domains": list(self.web_research_allowed_domains),
                "blocked_domains": list(self.web_research_blocked_domains),
            },
        }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_ai_config(path: str | Path) -> AIProviderConfig:
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"AI config not found: {config_path.resolve(strict=False)}")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AIConfigurationError("AI config file must contain a JSON object.")
    ai_data = data.get("ai", data)
    if not isinstance(ai_data, dict):
        raise AIConfigurationError("Top-level 'ai' configuration must be a JSON object.")
    return AIProviderConfig.from_dict(ai_data)
