from __future__ import annotations

from typing import Any

from preservation_risk_manager.frameworks import AnswerOption, Question, RiskFramework


def _supplied_answer_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        answer_id = value.get("answer_id") or value.get("id")
        return str(answer_id) if answer_id is not None else None
    return str(value)


def _answer_for_question(question: Question, supplied_id: str | None, unknown_id: str) -> tuple[AnswerOption | None, bool]:
    if supplied_id is None:
        return question.unknown_answer(unknown_id), True
    return question.answer_by_id(supplied_id), False


def score_answers(framework: RiskFramework, answers: dict[str, Any]) -> dict[str, Any]:
    """Score supplied answer IDs against a validated framework.

    The scorer accepts only framework-declared answer IDs. Missing answers are
    treated as abstentions when the question provides an unknown/abstention
    option; otherwise they are recorded as missing with zero points. The LLM, if
    added later, will only supply controlled answer IDs into this function.
    """
    question_results: list[dict[str, Any]] = []
    total_score = 0.0
    answered_questions = 0
    abstention_count = 0
    critical_abstention_count = 0
    missing_count = 0

    for question in framework.questions:
        supplied_id = _supplied_answer_id(answers.get(question.id))
        answer, missing = _answer_for_question(question, supplied_id, framework.unknown_answer_id)
        if missing:
            missing_count += 1

        if answer is None:
            points = 0.0
            weighted_points = 0.0
            answer_id = None
            abstention = True
        else:
            points = answer.points
            weighted_points = answer.points * question.weight
            answer_id = answer.id
            abstention = answer.abstention

        if not abstention:
            answered_questions += 1
        else:
            abstention_count += 1
            if question.critical:
                critical_abstention_count += 1

        total_score += weighted_points
        question_results.append({
            "question_id": question.id,
            "answer_id": answer_id,
            "points": points,
            "weight": question.weight,
            "weighted_points": weighted_points,
            "critical": question.critical,
            "abstention": abstention,
            "missing": missing,
        })

    total_questions = len(framework.questions)
    evidence_completeness = answered_questions / total_questions if total_questions else 0.0
    analysis_status = _analysis_status(
        answered_questions=answered_questions,
        abstention_count=abstention_count,
        critical_abstention_count=critical_abstention_count,
    )
    analysed_band = None if analysis_status in {"Not Assessed", "Needs Assessment"} else framework.band_for_score(total_score)

    return {
        "framework_id": framework.framework_id,
        "framework_version": framework.version,
        "score": total_score,
        "max_score": framework.max_score,
        "analysed_band": analysed_band,
        "analysis_status": analysis_status,
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "missing_count": missing_count,
        "abstention_count": abstention_count,
        "critical_abstention_count": critical_abstention_count,
        "evidence_completeness": evidence_completeness,
        "question_results": question_results,
    }


def _analysis_status(*, answered_questions: int, abstention_count: int, critical_abstention_count: int) -> str:
    if answered_questions == 0:
        return "Not Assessed"
    if critical_abstention_count:
        return "Needs Assessment"
    if abstention_count:
        return "Partially Assessed"
    return "Assessed"
