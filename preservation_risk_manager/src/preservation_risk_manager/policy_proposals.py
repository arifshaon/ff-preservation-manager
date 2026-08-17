from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _analysis_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_status": analysis.get("analysis_status"),
        "analysed_band": analysis.get("analysed_band"),
        "band_suppressed_reason": analysis.get("band_suppressed_reason"),
        "score": analysis.get("score"),
        "evidence_completeness": analysis.get("evidence_completeness"),
        "answered_questions": analysis.get("answered_questions"),
        "missing_count": analysis.get("missing_count"),
        "critical_abstention_count": analysis.get("critical_abstention_count"),
    }


def _action_from_posture(posture: str | None) -> dict[str, str]:
    normalized = str(posture or "Needs Assessment").strip().lower()
    if normalized == "low":
        return {
            "action_id": "take_no_action_now",
            "label": "Take no preservation action now",
            "rationale": "The current deterministic analysis indicates low preservation risk. Keep normal monitoring in place.",
        }
    if normalized == "moderate":
        return {
            "action_id": "monitor",
            "label": "Monitor format and evidence changes",
            "rationale": "The current deterministic analysis indicates moderate risk. Monitor evidence, holdings, and policy triggers before migration planning.",
        }
    if normalized == "high":
        return {
            "action_id": "plan_migration",
            "label": "Plan preservation action or migration pathway",
            "rationale": "The current deterministic analysis indicates high risk. Prepare a preservation action plan before committing to execution.",
        }
    return {
        "action_id": "needs_assessment",
        "label": "Complete preservation assessment",
        "rationale": "The current deterministic analysis does not support a confident band. Add evidence or review criteria before recommending action.",
    }


def _format_id(format_doc: dict[str, Any]) -> str:
    return str(format_doc.get("format_id") or format_doc.get("canonical_id") or format_doc.get("id") or "unknown-format")


def _format_name(format_doc: dict[str, Any]) -> str | None:
    value = format_doc.get("label") or format_doc.get("preferred_name") or format_doc.get("name")
    return str(value) if value is not None else None


def _policy_id(*, scope: str, institution_id: str | None, format_id: str) -> str:
    owner = institution_id or scope or "global"
    safe_format = format_id.replace("/", "-").replace(" ", "-")
    return f"draft-policy-{owner}-{safe_format}-{_utc_stamp()}"


def build_policy_change_proposal(
    *,
    goal: str,
    resolution: dict[str, Any],
    format_doc: dict[str, Any],
    scope: str,
    evidence_hash: str,
    analysis: dict[str, Any],
    criterion_claim_canonical_ids: list[str],
    criterion_claims_summary: dict[str, Any],
    derived_answers: dict[str, Any],
    institution_id: str | None = None,
    readiness_status: str = "Unknown",
    exposure_level: str = "Unknown",
    local_risk_posture: str | None = None,
) -> dict[str, Any]:
    """Build an evidence-grounded draft policy proposal package.

    This function deliberately does not call an LLM and does not write policy.
    It creates the bounded context, draft record, and approval contract that an
    LLM or a human reviewer can use safely.
    """
    format_id = _format_id(format_doc)
    posture_for_action = local_risk_posture or analysis.get("analysed_band") or "Needs Assessment"
    action = _action_from_posture(posture_for_action)
    policy_id = _policy_id(scope=scope, institution_id=institution_id, format_id=format_id)
    specificity = 4 if format_id != "unknown-format" else (1 if institution_id else 0)

    policy_record: dict[str, Any] = {
        "policy_id": policy_id,
        "policy_type": "action_recommendation",
        "review_status": "draft",
        "scope": scope,
        "institution_id": institution_id,
        "target": {
            "canonical_id": format_id,
            "preferred_name": _format_name(format_doc),
        },
        "specificity": specificity,
        "mode": "supplement",
        "goal": goal,
        "basis": {
            "evidence_hash": evidence_hash,
            "analysis": _analysis_summary(analysis),
            "readiness_status": readiness_status if institution_id else None,
            "exposure_level": exposure_level if institution_id else None,
            "local_risk_posture": local_risk_posture,
            "criterion_claim_canonical_ids": criterion_claim_canonical_ids,
            "criterion_claims_used": criterion_claims_summary.get("total_claims", 0),
        },
        "actions": [
            {
                "action_id": action["action_id"],
                "label": action["label"],
                "rationale": action["rationale"],
                "drafted_from": "deterministic_analysis_context",
            }
        ],
        "approval": {
            "approved_by": None,
            "effective_from": None,
            "supersedes": None,
            "review_status": "draft",
        },
    }

    llm_context = {
        "goal": goal,
        "format": format_doc,
        "scope": scope,
        "institution_id": institution_id,
        "readiness_status": readiness_status if institution_id else None,
        "exposure_level": exposure_level if institution_id else None,
        "local_risk_posture": local_risk_posture,
        "analysis": analysis,
        "derived_answers": derived_answers,
        "criterion_claims_summary": criterion_claims_summary,
        "evidence_hash": evidence_hash,
    }

    return {
        "status": "draft",
        "proposal_type": "policy_change",
        "llm_execution": "not_invoked",
        "llm_role": "draft_policy_recommendation_from_bounded_context",
        "write_status": "not_written",
        "approval_required": True,
        "approval_requirements": {
            "required_fields": ["approved_by", "effective_from", "review_status"],
            "required_review_status": "approved",
            "notes": "This command prepares a draft only. Policy records must not be promoted or written until a human approves the exact diff.",
        },
        "resolution": resolution,
        "affected_formats": [
            {
                "canonical_id": format_id,
                "preferred_name": _format_name(format_doc),
            }
        ],
        "analysis_context": {
            "scope": scope,
            "institution_id": institution_id,
            "readiness_status": readiness_status if institution_id else None,
            "exposure_level": exposure_level if institution_id else None,
            "local_risk_posture": local_risk_posture,
            "evidence_hash": evidence_hash,
            "analysis": _analysis_summary(analysis),
            "criterion_claims_summary": criterion_claims_summary,
            "criterion_claim_canonical_ids": criterion_claim_canonical_ids,
        },
        "llm_prompt": {
            "system": (
                "You are a preservation policy drafting assistant. Use only the supplied JSON context. "
                "Do not change deterministic analysis results, evidence hashes, scores, bands, local risk posture, "
                "or criterion claim provenance. Draft recommendation text only, and identify uncertainty explicitly."
            ),
            "user": {
                "task": "Review the bounded preservation-risk context and draft a policy/action recommendation for human approval.",
                "constraints": [
                    "Do not invent evidence.",
                    "Do not change analysed_band or local_risk_posture.",
                    "Do not mark the policy approved.",
                    "Return a draft recommendation that can be represented as the proposed policy record.",
                ],
                "context": llm_context,
            },
        },
        "proposed_policy_record": policy_record,
        "proposed_diff": [
            {
                "op": "add",
                "path": "/policy_records/-",
                "value": policy_record,
            }
        ],
    }
