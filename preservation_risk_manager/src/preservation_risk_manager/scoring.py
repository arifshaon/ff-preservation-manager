from __future__ import annotations

from typing import Any

from preservation_risk_manager.frameworks import AnswerOption, Question, RiskFramework


def _supplied_answer(value: Any) -> tuple[str | None, bool, str | None]:
    if value is None:
        return None, False, None
    if isinstance(value, str):
        return value, False, None
    if isinstance(value, dict):
        answer_id = value.get("answer_id") or value.get("id")
        status = value.get("derivation_status") or value.get("status")
        missing = bool(value.get("missing", False)) or status == "missing_evidence"
        return (str(answer_id) if answer_id is not None else None, missing, str(status) if status is not None else None)
    return str(value), False, None


def _answer_for_question(question: Question, supplied_id: str | None, unknown_id: str) -> tuple[AnswerOption | None, bool]:
    if supplied_id is None:
        return question.unknown_answer(unknown_id), True
    return question.answer_by_id(supplied_id), False


def _band_suppressed_reason(
    *,
    framework: RiskFramework,
    analysis_status: str,
    evidence_completeness: float,
    min_completeness_for_band: float,
) -> str | None:
    if not framework.banding_enabled:
        return "framework_not_calibrated"
    if analysis_status == "Not Assessed":
        return "not_assessed"
    if analysis_status == "Needs Assessment":
        return "critical_abstention"
    if evidence_completeness < min_completeness_for_band:
        return "insufficient_evidence_completeness"
    return None


def score_answers(framework: RiskFramework, answers: dict[str, Any]) -> dict[str, Any]:
    """Score supplied answer IDs against a validated framework.

    The scorer accepts only framework-declared answer IDs. Missing answers are
    treated as abstentions when the question provides an unknown/abstention
    option; otherwise they are recorded as missing with zero points. A framework
    may explicitly disable overall banding while its question set is being
    calibrated; question-level answers and completeness remain available, but no
    authoritative Low/Moderate/High band is emitted.
    """
    question_results: list[dict[str, Any]] = []
    total_score = 0.0
    answered_questions = 0
    abstention_count = 0
    critical_abstention_count = 0
    missing_count = 0

    for question in framework.questions:
        supplied_id, supplied_missing, derivation_status = _supplied_answer(answers.get(question.id))
        answer, inferred_missing = _answer_for_question(question, supplied_id, framework.unknown_answer_id)
        missing = inferred_missing or supplied_missing
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
        result = {
            "question_id": question.id,
            "answer_id": answer_id,
            "points": points,
            "weight": question.weight,
            "weighted_points": weighted_points,
            "critical": question.critical,
            "abstention": abstention,
            "missing": missing,
        }
        if derivation_status:
            result["derivation_status"] = derivation_status
        question_results.append(result)

    total_questions = len(framework.questions)
    evidence_completeness = answered_questions / total_questions if total_questions else 0.0
    analysis_status = _analysis_status(
        answered_questions=answered_questions,
        abstention_count=abstention_count,
        critical_abstention_count=critical_abstention_count,
    )
    band_suppressed_reason = _band_suppressed_reason(
        framework=framework,
        analysis_status=analysis_status,
        evidence_completeness=evidence_completeness,
        min_completeness_for_band=framework.min_completeness_for_band,
    )
    analysed_band = None if band_suppressed_reason else framework.band_for_score(total_score)

    return {
        "framework_id": framework.framework_id,
        "framework_version": framework.version,
        "calibration_status": framework.calibration_status,
        "banding_enabled": framework.banding_enabled,
        "scale_direction": framework.scale_direction,
        "score": total_score,
        "max_score": framework.max_score,
        "analysed_band": analysed_band,
        "band_suppressed_reason": band_suppressed_reason,
        "analysis_status": analysis_status,
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "missing_count": missing_count,
        "abstention_count": abstention_count,
        "critical_abstention_count": critical_abstention_count,
        "evidence_completeness": evidence_completeness,
        "min_completeness_for_band": framework.min_completeness_for_band,
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
