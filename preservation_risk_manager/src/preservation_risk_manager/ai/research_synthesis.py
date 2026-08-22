"""Backward-compatible import path for capability-driven AI synthesis.

The public implementation lives in :mod:`preservation_risk_manager.ai.capability_result`,
which wraps the single-call provider implementation with deterministic consistency
checks and capability/source audit normalization. This module intentionally contains
no separate research workflow so historical imports cannot reintroduce the former
two-call behavior.
"""

from preservation_risk_manager.ai.capability_result import (
    synthesize_with_capabilities,
    synthesize_with_web_research,
)

__all__ = ["synthesize_with_capabilities", "synthesize_with_web_research"]
