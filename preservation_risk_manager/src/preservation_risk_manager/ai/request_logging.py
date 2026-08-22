from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIWebResearchResponse,
)


def _request_payload(request: AIRequest) -> dict[str, Any]:
    return {
        "messages": [message.to_dict() for message in request.messages],
        "tools": [tool.to_openai_tool() for tool in request.tools],
        "required_tool_name": request.required_tool_name,
        "response_schema_name": request.response_schema_name,
        "response_schema": request.response_schema,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
    }


class AIRequestLoggingProvider(AIProvider):
    """Opt-in provider wrapper that appends exact AI inputs as JSON Lines.

    The wrapper records application/model inputs immediately before delegating the
    call. Credentials are never included. The log is deliberately append-only so
    one CLI invocation can preserve routing, identification, question-level, and
    synthesis calls in execution order.
    """

    def __init__(self, delegate: AIProvider, log_path: str | Path) -> None:
        self.delegate = delegate
        self.log_path = Path(log_path).expanduser()
        self.provider_name = delegate.provider_name
        self.capabilities = delegate.capabilities
        # Preserve provider configuration access for TPM budgeting and other
        # capability-aware orchestration.
        if hasattr(delegate, "config"):
            self.config = getattr(delegate, "config")
        self._sequence = 0
        self._prepare_log_path()

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    def _prepare_log_path(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8"):
                pass
        except OSError as exc:
            raise AIProviderError(f"Could not open AI input log file '{self.log_path}': {exc}") from exc

    def _append(self, call_type: str, payload: dict[str, Any]) -> None:
        self._sequence += 1
        record = {
            "sequence": self._sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "call_type": call_type,
            "provider": self.delegate.provider_name,
            "model": self.delegate.model_name,
            **payload,
        }
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
                handle.write("\n")
        except OSError as exc:
            raise AIProviderError(f"Could not write AI input log file '{self.log_path}': {exc}") from exc

    def _effective_domains(
        self,
        allowed_domains: tuple[str, ...],
        blocked_domains: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        config = getattr(self.delegate, "config", None)
        effective_allowed = tuple(allowed_domains)
        effective_blocked = tuple(blocked_domains)
        if config is not None:
            if not effective_allowed:
                effective_allowed = tuple(getattr(config, "external_research_allowed_domains", ()) or ())
            if not effective_blocked:
                effective_blocked = tuple(getattr(config, "external_research_blocked_domains", ()) or ())
        return effective_allowed, effective_blocked

    def generate(self, request: AIRequest) -> AIResponse:
        self._append("generate", {"request": _request_payload(request)})
        return self.delegate.generate(request)

    def generate_with_capabilities(
        self,
        request: AIRequest,
        *,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
    ) -> AIResponse:
        effective_allowed, effective_blocked = self._effective_domains(allowed_domains, blocked_domains)
        self._append(
            "generate_with_capabilities",
            {
                "request": _request_payload(request),
                "capability_options": {
                    "web_search": True,
                    "allowed_domains": list(effective_allowed),
                    "blocked_domains": list(effective_blocked),
                    "tool_choice": "auto",
                },
            },
        )
        method = getattr(self.delegate, "generate_with_capabilities", None)
        if not callable(method):
            return self.delegate.generate(request)
        return method(
            request,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )

    def research_web(
        self,
        prompt: str,
        *,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
    ) -> AIWebResearchResponse:
        effective_allowed, effective_blocked = self._effective_domains(allowed_domains, blocked_domains)
        self._append(
            "research_web",
            {
                "prompt": prompt,
                "capability_options": {
                    "web_search": True,
                    "allowed_domains": list(effective_allowed),
                    "blocked_domains": list(effective_blocked),
                    "tool_choice": "auto",
                },
            },
        )
        return self.delegate.research_web(
            prompt,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )

    def describe(self) -> dict[str, Any]:
        result = dict(self.delegate.describe())
        result["input_logging"] = {
            "enabled": True,
            "path": str(self.log_path),
            "format": "jsonl",
        }
        return result


def with_ai_request_logging(provider: AIProvider, log_path: str | Path | None) -> AIProvider:
    """Return provider unchanged unless an explicit log path was supplied."""
    if log_path is None or not str(log_path).strip():
        return provider
    if isinstance(provider, AIRequestLoggingProvider):
        return provider
    return AIRequestLoggingProvider(provider, log_path)
