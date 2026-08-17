from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.ai.base import AIProvider, AIProviderError
from preservation_risk_manager.ai.risk_analysis import interpret_question_with_ai
from preservation_risk_manager.frameworks import RiskFramework


def review_answers_with_ai(
    provider: AIProvider,
    framework: RiskFramework,
    evidence_pack: dict[str, Any],
    deterministic_answer_document: dict[str, Any],
    *,
    max_evidence_items: int = 20,
) -> dict[str, Any]:
    """Independently review all framework questions without changing scoring answers.

    This mode is for calibration and audit. The AI receives the same bounded,
    application-supplied evidence used by the fill-gaps interpreter, but its
    answer is recorded only as a comparison against the deterministic answer.
    Deterministic answers and scoring inputs remain unchanged even when the AI
    disagrees.
    """
    result = deepcopy(deterministic_answer_document)
    derivation = result.setdefault("derivation", {})

    summary = {
        "mode": "review_all",
        "provider": provider.describe(),
        "eligible_questions": len(framework.questions),
        "attempted_questions": 0,
        "reviewed_questions": 0,
        "agreements": 0,
        "divergences": 0,
        "ai_abstentions": 0,
        "skipped_no_evidence": 0,
        "failed_questions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    audit: dict[str, Any] = {}

    for question in framework.questions:
        deterministic_result = derivation.get(question.id) or {}
        deterministic_answer_id = deterministic_result.get("answer_id")
        deterministic_status = str(deterministic_result.get("status") or "")

        try:
            ai_result = interpret_question_with_ai(
                provider,
                framework,
                question,
                evidence_pack,
                deterministic_result,
                max_evidence_items=max_evidence_items,
            )
        except (AIProviderError, ValueError) as exc:
            summary["attempted_questions"] += 1
            summary["failed_questions"] += 1
            audit[question.id] = {
                "status": "failed",
                "error": str(exc),
                "deterministic_answer_id": deterministic_answer_id,
                "deterministic_status": deterministic_status,
            }
            continue

        if ai_result["status"] == "skipped_no_evidence":
            summary["skipped_no_evidence"] += 1
            audit[question.id] = {
                **ai_result,
                "comparison": "not_reviewed",
                "agreement": None,
                "deterministic_answer_id": deterministic_answer_id,
                "deterministic_status": deterministic_status,
            }
            continue

        summary["attempted_questions"] += 1
        summary["reviewed_questions"] += 1
        usage = ai_result.get("usage") or {}
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            summary[field] += int(usage.get(field) or 0)

        ai_answer_id = str(ai_result["answer_id"])
        ai_answer = question.answer_by_id(ai_answer_id)
        if ai_answer.abstention:
            summary["ai_abstentions"] += 1

        agreement = ai_answer_id == deterministic_answer_id
        comparison = "agreement" if agreement else "divergence"
        summary["agreements" if agreement else "divergences"] += 1

        audit[question.id] = {
            **ai_result,
            "comparison": comparison,
            "agreement": agreement,
            "deterministic_answer_id": deterministic_answer_id,
            "deterministic_status": deterministic_status,
        }

    result["derivation_method"] = "deterministic_with_ai_review"
    result["ai_summary"] = summary
    result["ai_audit"] = audit
    return result
