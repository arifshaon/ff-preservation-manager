"""Preservation risk manager.

This package owns deterministic preservation-risk analysis guardrails and
action-policy resolution. The format registry remains the evidence source; the
manager interprets that evidence and computes institution-specific posture and
action recommendations.
"""

__all__ = [
    "actions",
    "cli",
    "currency",
    "data_access",
    "errors",
    "evidence_packs",
    "format_resolver",
    "frameworks",
    "posture",
    "responses",
    "scoring",
]
