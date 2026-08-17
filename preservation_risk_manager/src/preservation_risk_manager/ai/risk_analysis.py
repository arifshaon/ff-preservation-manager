from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from preservation_risk_manager.ai.base import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResponse,
)
from preservation_risk_manager.answer_derivation import evidence_items
from preservation_risk_manager.frameworks import Question, RiskFramework


AI_ELIGIBLE_STATUSES = {
    "unknown",
    "missing_evidence",
    "derived_conflict_conservative",
}

RISK_INTERPRETER_SYSTEM_PROMPT = (
    "You are an evidence interpreter inside a file-format preservation risk system. "
    "Use only the evidence items supplied by the application. Never use general knowledge, "
    "memory, unstated assumptions, web knowledge, or the risk score itself. Choose exactly "
    "one allowed controlled answer. If the supplied evidence cannot support a non-abstention "
    "answer, choose the framework's unknown/abstention answer. Cite only evidence refs that "
    "appear in the supplied evidence list. Do not calculate risk scores, bands, posture, or actions."
)


def _json_safe(value: Any, *, max_string: int = 2500) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "…"
    if isinstance(value, dict):
        return {str(key): _json_safe(item, max_string=max_string) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, max_string=max_string) for item in list(value)[:50]]
    return _json_safe(str(value), max_string=max_string)


def _claim_matches_question(claim: dict[str, Any], question: Question) -> bool:
    fields = {
        str(value)
        for key in ("criterion_id", "field", "evidence_field", "path")
        if (value := claim.get(key)) is not None
    }
    return bool(fields.intersection(question.evidence_fields))


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        safe = _json_safe(item)
        key = json.dumps(safe, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(safe)
    return result


def question_evidence(
    question: Question,
    evidence_pack: dict[str, Any],
    deterministic_result: dict[str, Any],
    *,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Return bounded, reference-addressable evidence for one framework question.

    Explicit deterministic matches are preferred. If none exist, evidence with a
    matching criterion/field is used. As a final fallback, the bounded evidence
    pack is exposed so AI can interpret descriptive evidence that has not yet
    been normalized into a criterion claim. The model is still forbidden from
    using facts outside these supplied items.
    """
    preferred = [
        item
        for item in deterministic_result.get("evidence_claims", [])
        if isinstance(item, dict)
    ]
    all_items = evidence_items(evidence_pack)
    matching = [item for item in all_items if _claim_matches_question(item, question)]
    selected = _dedupe_evidence(preferred + matching)
    if not selected:
        selected = _dedupe_evidence(all_items)
    selected = selected[:max_items]
    return [
        {"ref": f"E{index:03d}", "evidence": item}
        for index, item in enumerate(selected, start=1)
    ]


def _response_schema(question: Question) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "question_id": {"type": "string", "enum": [question.id]},
            "answer_id": {
                "type": "string",
                "enum": [answer.id for answer in question.answers],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainty": {"type": "string"},
        },
        "required": [
            "question_id",
            "answer_id",
            "confidence",
            "rationale",
            "evidence_refs",
            "uncertainty",
        ],
        "additionalProperties": False,
    }


def _question_prompt(
    framework: RiskFramework,
    question: Question,
    evidence_pack: dict[str, Any],
    deterministic_result: dict[str, Any],
    referenced_evidence: list[dict[str, Any]],
) -> str:
    context = {
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "unknown_answer_id": framework.unknown_answer_id,
        },
        "format": _json_safe(evidence_pack.get("format") or {}),
        "scope": evidence_pack.get("scope", "global"),
        "institution_id": evidence_pack.get("institution_id"),
        "question": {
            "id": question.id,
            "label": question.label,
            "critical": question.critical,
            "evidence_fields": list(question.evidence_fields),
            "allowed_answers": [
                {
                    "id": answer.id,
                    "label": answer.label,
                    "abstention": answer.abstention,
                }
                for answer in question.answers
            ],
        },
        "deterministic_result": {
            "answer_id": deterministic_result.get("answer_id"),
            "status": deterministic_result.get("status"),
            "conflicting_answer_ids": deterministic_result.get("conflicting_answer_ids", []),
        },
        "evidence": referenced_evidence,
    }
    return (
        "Interpret the supplied evidence for this one framework question. "
        "Return only the required structured response. For a non-abstention answer, "
        "evidence_refs must contain at least one supplied ref that directly supports the choice. "
        "If support is insufficient or contradictory in a way you cannot resolve from the supplied "
        "evidence, choose the unknown/abstention answer.\n\n"
        + json.dumps(context, indent=2, sort_keys=True, default=str)
    )


def _validate_ai_answer(
    question: Question,
    framework: RiskFramework,
    response: AIResponse,
    referenced_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    data = response.structured
    if not isinstance(data, dict):
        raise AIProviderError("AI risk answer did not return a structured JSON object.")

    if str(data.get("question_id")) != question.id:
        raise AIProviderError(
            f"AI risk answer returned question_id '{data.get('question_id')}' instead of '{question.id}'."
        )

    allowed_answers = {answer.id: answer for answer in question.answers}
    answer_id = str(data.get("answer_id") or "")
    if answer_id not in allowed_answers:
        raise AIProviderError(
            f"AI risk answer '{answer_id}' is not allowed for question '{question.id}'."
        )

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIProviderError("AI risk answer confidence must be numeric.") from exc
    if not 0 <= confidence <= 1:
        raise AIProviderError("AI risk answer confidence must be between 0 and 1.")

    evidence_refs_raw = data.get("evidence_refs")
    if not isinstance(evidence_refs_raw, list):
        raise AIProviderError("AI risk answer evidence_refs must be an array.")
    evidence_refs = [str(ref) for ref in evidence_refs_raw]
    known_refs = {entry["ref"] for entry in referenced_evidence}
    unknown_refs = sorted(set(evidence_refs) - known_refs)
    if unknown_refs:
        raise AIProviderError(
            "AI risk answer cited evidence refs not supplied by the application: "
            + ", ".join(unknown_refs)
        )

    answer = allowed_answers[answer_id]
    if not answer.abstention and not evidence_refs:
        raise AIProviderError(
            f"AI risk answer '{answer_id}' requires at least one supplied evidence reference."
        )

    evidence_by_ref = {entry["ref"]: entry["evidence"] for entry in referenced_evidence}
    return {
        "question_id": question.id,
        "answer_id": answer_id,
        "confidence": confidence,
        "rationale": str(data.get("rationale") or ""),
        "evidence_refs": evidence_refs,
        "cited_evidence": [evidence_by_ref[ref] for ref in evidence_refs],
        "uncertainty": str(data.get("uncertainty") or ""),
        "provider": response.provider,
        "model": response.model,
        "usage": response.to_dict()["usage"],
    }


def interpret_question_with_ai(
    provider: AIProvider,
    framework: RiskFramework,
    question: Question,
    evidence_pack: dict[str, Any],
    deterministic_result: dict[str, Any],
    *,
    max_evidence_items: int = 20,
) -> dict[str, Any]:
    referenced_evidence = question_evidence(
        question,
        evidence_pack,
        deterministic_result,
        max_items=max_evidence_items,
    )
    if not referenced_evidence:
        return {
            "status": "skipped_no_evidence",
            "question_id": question.id,
            "answer_id": deterministic_result.get("answer_id"),
        }

    request = AIRequest(
        messages=(
            AIMessage("system", RISK_INTERPRETER_SYSTEM_PROMPT),
            AIMessage(
                "user",
                _question_prompt(
                    framework,
                    question,
                    evidence_pack,
                    deterministic_result,
                    referenced_evidence,
                ),
            ),
        ),
        response_schema=_response_schema(question),
        response_schema_name="preservation_risk_answer",
        temperature=0.0,
    )
    response = provider.generate(request)
    validated = _validate_ai_answer(question, framework, response, referenced_evidence)
    validated["status"] = (
        "abstained" if question.answer_by_id(validated["answer_id"]).abstention else "accepted"
    )
    return validated


def derive_answers_with_ai(
    provider: AIProvider,
    framework: RiskFramework,
    evidence_pack: dict[str, Any],
    deterministic_answer_document: dict[str, Any],
    *,
    max_evidence_items: int = 20,
) -> dict[str, Any]:
    """Use AI only for unresolved/ambiguous questions, then return controlled answers.

    Deterministically derived answers remain authoritative and are never sent for
    replacement in this mode. AI may fill unknown/missing questions or resolve a
    deterministic conflict, but every accepted non-abstention answer must cite
    evidence supplied by the application. Provider/validation failures preserve
    the original deterministic answer.
    """
    result = deepcopy(deterministic_answer_document)
    answers = result.setdefault("answers", {})
    scoring_answers = result.setdefault("scoring_answers", {})
    derivation = result.setdefault("derivation", {})

    summary = {
        "provider": provider.describe(),
        "eligible_questions": 0,
        "attempted_questions": 0,
        "accepted_answers": 0,
        "abstentions": 0,
        "skipped_no_evidence": 0,
        "failed_questions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    audit: dict[str, Any] = {}

    for question in framework.questions:
        deterministic_result = derivation.get(question.id) or {}
        previous_status = str(deterministic_result.get("status") or "")
        if previous_status not in AI_ELIGIBLE_STATUSES:
            continue

        summary["eligible_questions"] += 1
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
                "previous_status": previous_status,
                "previous_answer_id": deterministic_result.get("answer_id"),
            }
            continue

        if ai_result["status"] == "skipped_no_evidence":
            summary["skipped_no_evidence"] += 1
            audit[question.id] = {
                **ai_result,
                "previous_status": previous_status,
                "previous_answer_id": deterministic_result.get("answer_id"),
            }
            continue

        summary["attempted_questions"] += 1
        usage = ai_result.get("usage") or {}
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            summary[field] += int(usage.get(field) or 0)

        answer_id = str(ai_result["answer_id"])
        answer = question.answer_by_id(answer_id)
        if answer.abstention:
            summary["abstentions"] += 1
            new_status = "ai_abstained"
        else:
            summary["accepted_answers"] += 1
            new_status = "ai_interpreted"

        answers[question.id] = answer_id
        scoring_answers[question.id] = {
            "answer_id": answer_id,
            "derivation_status": new_status,
            "missing": answer.abstention and previous_status == "missing_evidence",
        }
        derivation[question.id] = {
            "answer_id": answer_id,
            "status": new_status,
            "previous_status": previous_status,
            "previous_answer_id": deterministic_result.get("answer_id"),
            "evidence_fields": list(question.evidence_fields),
            "evidence_claims": ai_result.get("cited_evidence") or deterministic_result.get("evidence_claims", []),
            "ai": {
                key: value
                for key, value in ai_result.items()
                if key not in {"cited_evidence", "status"}
            },
        }
        audit[question.id] = {
            **ai_result,
            "previous_status": previous_status,
            "previous_answer_id": deterministic_result.get("answer_id"),
        }

    result["derivation_method"] = "deterministic_then_ai_evidence_interpretation"
    result["ai_summary"] = summary
    result["ai_audit"] = audit
    return result
