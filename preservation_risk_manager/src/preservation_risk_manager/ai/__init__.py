"""Provider-neutral AI interface for preservation-risk workflows."""

from preservation_risk_manager.ai.base import (
    AIConfigurationError,
    AIError,
    AIMessage,
    AIProvider,
    AIProviderCapabilities,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIToolCall,
    AIToolDefinition,
    AIUsage,
)
from preservation_risk_manager.ai.config import AIProviderConfig, load_ai_config
from preservation_risk_manager.ai.factory import build_ai_provider
from preservation_risk_manager.ai.review import review_answers_with_ai
from preservation_risk_manager.ai.risk_analysis import (
    AI_ELIGIBLE_STATUSES,
    derive_answers_with_ai,
    interpret_question_with_ai,
    question_evidence,
)
from preservation_risk_manager.ai.synthesis import build_synthesis_evidence, synthesize_with_ai

__all__ = [
    "AIConfigurationError",
    "AIError",
    "AIMessage",
    "AIProvider",
    "AIProviderCapabilities",
    "AIProviderConfig",
    "AIProviderError",
    "AIRequest",
    "AIResponse",
    "AIToolCall",
    "AIToolDefinition",
    "AIUsage",
    "AI_ELIGIBLE_STATUSES",
    "build_ai_provider",
    "build_synthesis_evidence",
    "derive_answers_with_ai",
    "interpret_question_with_ai",
    "load_ai_config",
    "question_evidence",
    "review_answers_with_ai",
    "synthesize_with_ai",
]
