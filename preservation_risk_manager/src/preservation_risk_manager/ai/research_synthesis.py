"""Backward-compatible import path for capability-driven AI synthesis.

The active implementation lives in :mod:`preservation_risk_manager.ai.capability_synthesis`.
This module intentionally contains no separate research workflow so historical
imports cannot accidentally reintroduce the former two-call behavior.
"""

from preservation_risk_manager.ai.capability_synthesis import (
    synthesize_with_capabilities,
    synthesize_with_web_research,
)

__all__ = ["synthesize_with_capabilities", "synthesize_with_web_research"]
