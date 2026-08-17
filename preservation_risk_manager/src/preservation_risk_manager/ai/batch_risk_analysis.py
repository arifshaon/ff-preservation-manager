from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Callable

from preservation_risk_manager.ai.base import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIRequest,
)
from preservation_risk_manager.ai.risk_analysis import AI_ELIGIBLE_STATUSES, question_evidence
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_identification import enrich_candidate_from_source_records
from preservation_risk_manager.scoring import score_answers
from preservation_risk_manager.source_evidence import build_ai_source_evidence


BATCH_RISK_SYSTEM_PROMPT = (
    "You are an evidence interpreter inside a file-format preservation risk system. "
    "The application has already identified a bounded set of PRONOM PUIDs. Your task is to answer the supplied "
    "framework questions for those PUIDs using only the evidence supplied for each PUID/question pair. Never use "
    "general knowledge, memory, web knowledge, or evidence from one PUID to answer another PUID unless that evidence "
    "is explicitly supplied under that PUID. Respect format version. Prefer direct/exact-authority evidence over "
    "broader family evidence for version-specific properties. If evidence is insufficient, return the question's "
    "unknown/abstention answer. Cite only evidence refs supplied for the same PUID and question. Do not calculate risk "
    "scores, risk bands, policy, or preservation actions; the application does that deterministically after your answers."
)


def _format_context(format_doc: dict[str, Any], puid: str) -> dict[str, Any]:
    return {
        "puid": puid,
        "canonical_id": format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id"),
        "label": format_doc.get("preferred_name") or format_doc.get("format_name") or format_doc.get("name") or format_doc.get("label"),
        "version": format_doc.get("version"),
        "versions": format_doc.get("versions") or [],
        "internal_signature_names": format_doc.get("internal_signature_names") or [],
        "identifiers": format_doc.get("identifiers") or {},
    }


def _prepare_case(
    reader,
    framework,
    candidate: dict[str, Any],
    request: dict[str, Any],
    *,
    max_evidence_items: int,
) -> dict[str, Any]:
    format_doc = candidate.get("format_doc") or {}
    try:
        format_doc = enrich_candidate_from_source_records(reader, format_doc)
    except Exception:
        format_doc = dict(format_doc)

    institution_id = request.get("institution_id") if request.get("scope") == "institution" else None
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(format_doc, institution_id=institution_id, criterion_claims=claims)
    if format_doc.get("version") is not None:
        pack["format"]["version"] = str(format_doc.get("version"))
    if format_doc.get("versions"):
        pack["format"]["versions"] = [str(value) for value in format_doc.get("versions")]
    if format_doc.get("internal_signature_names"):
        pack["format"]["internal_signature_names"] = [str(value) for value in format_doc.get("internal_signature_names")]

    deterministic = derive_answers(framework, pack)
    deterministic_analysis = score_answers(
        framework,
        deterministic.get("scoring_answers") or deterministic["answers"],
    )

    source_evidence = build_ai_source_evidence(
        reader,
        format_doc,
        max_source_records=max(40, max_evidence_items * 3),
        max_items=max(60, max_evidence_items * 5),
    )
    pack["ai_source_evidence"] = source_evidence

    puid = str(candidate["puid"])
    question_payloads: list[dict[str, Any]] = []
    allowed_by_question: dict[str, set[str]] = {}
    evidence_by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    for question in framework.questions:
        deterministic_result = deterministic.get("derivation", {}).get(question.id) or {}
        if str(deterministic_result.get("status") or "") not in AI_ELIGIBLE_STATUSES:
            continue
        refs = question_evidence(
            question,
            pack,
            deterministic_result,
            max_items=max_evidence_items,
        )
        if not refs:
            continue
        renamed: list[dict[str, Any]] = []
        ref_map: dict[str, dict[str, Any]] = {}
        for index, entry in enumerate(refs, start=1):
            ref = f"{puid}|{question.id}|E{index:03d}"
            evidence = entry["evidence"]
            renamed.append({"ref": ref, "evidence": evidence})
            ref_map[ref] = evidence
        evidence_by_pair[question.id] = ref_map
        allowed_by_question[question.id] = {answer.id for answer in question.answers}
        question_payloads.append(
            {
                "question_id": question.id,
                "label": question.label,
                "evidence_fields": list(question.evidence_fields),
                "allowed_answers": [
                    {
                        "answer_id": answer.id,
                        "label": answer.label,
                        "abstention": answer.abstention,
                    }
                    for answer in question.answers
                ],
                "deterministic_status": deterministic_result.get("status"),
                "evidence": renamed,
            }
        )

    source_record_keys = {
        (str(item.get("source_id") or ""), str(item.get("source_record_id") or ""))
        for item in source_evidence
        if item.get("source_id") or item.get("source_record_id")
    }
    return {
        "puid": puid,
        "candidate": candidate,
        "format_doc": format_doc,
        "format": _format_context(format_doc, puid),
        "criterion_claims_used": len(claims),
        "ai_source_evidence_items": len(source_evidence),
        "ai_source_records_used": len(source_record_keys),
        "evidence_hash": evidence_hash(pack),
        "deterministic": deterministic,
        "deterministic_analysis": deterministic_analysis,
        "questions": question_payloads,
        "allowed_by_question": allowed_by_question,
        "evidence_by_pair": evidence_by_pair,
    }


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "puid": {"type": "string"},
                        "question_id": {"type": "string"},
                        "answer_id": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                        "uncertainty": {"type": "string"},
                    },
                    "required": [
                        "puid",
                        "question_id",
                        "answer_id",
                        "confidence",
                        "rationale",
                        "evidence_refs",
                        "uncertainty",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }


def _request_payload(user_question: str, cases: list[dict[str, Any]], framework) -> dict[str, Any]:
    return {
        "user_question": user_question,
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "unknown_answer_id": framework.unknown_answer_id,
        },
        "matched_puids": [case["puid"] for case in cases],
        "formats": [
            {
                "format": case["format"],
                "questions": case["questions"],
            }
            for case in cases
        ],
    }


def _validate_answers(response, cases: list[dict[str, Any]], framework) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    data = response.structured
    if not isinstance(data, dict) or not isinstance(data.get("answers"), list):
        raise AIProviderError("Batch AI risk response did not contain an answers array.")

    cases_by_puid = {case["puid"]: case for case in cases}
    question_by_id = {question.id: question for question in framework.questions}
    accepted: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    for item in data["answers"]:
        if not isinstance(item, dict):
            errors.append("non-object answer ignored")
            continue
        puid = str(item.get("puid") or "")
        question_id = str(item.get("question_id") or "")
        key = (puid, question_id)
        case = cases_by_puid.get(puid)
        question = question_by_id.get(question_id)
        if case is None or question is None or question_id not in case["allowed_by_question"]:
            errors.append(f"unknown pair {puid}/{question_id} ignored")
            continue
        answer_id = str(item.get("answer_id") or "")
        if answer_id not in case["allowed_by_question"][question_id]:
            errors.append(f"invalid answer {answer_id} for {puid}/{question_id} ignored")
            continue
        refs = [str(ref) for ref in item.get("evidence_refs") or []]
        known_refs = case["evidence_by_pair"].get(question_id, {})
        if any(ref not in known_refs for ref in refs):
            errors.append(f"invalid evidence ref for {puid}/{question_id} ignored")
            continue
        answer = question.answer_by_id(answer_id)
        if not answer.abstention and not refs:
            errors.append(f"non-abstention without evidence for {puid}/{question_id} ignored")
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            errors.append(f"invalid confidence for {puid}/{question_id} ignored")
            continue
        if not 0 <= confidence <= 1:
            errors.append(f"out-of-range confidence for {puid}/{question_id} ignored")
            continue
        accepted[key] = {
            "question_id": question_id,
            "answer_id": answer_id,
            "confidence": confidence,
            "rationale": str(item.get("rationale") or ""),
            "evidence_refs": refs,
            "cited_evidence": [known_refs[ref] for ref in refs],
            "uncertainty": str(item.get("uncertainty") or ""),
            "provider": response.provider,
            "model": response.model,
            "usage": response.to_dict()["usage"],
        }
    return accepted, errors


def _merge_case(case: dict[str, Any], answers: dict[tuple[str, str], dict[str, Any]], framework) -> dict[str, Any]:
    result = deepcopy(case["deterministic"])
    result["derivation_method"] = "deterministic_then_batched_ai_evidence_interpretation"
    summary = {
        "eligible_questions": len(case["questions"]),
        "accepted_answers": 0,
        "abstentions": 0,
        "unanswered_by_batch": 0,
    }
    audit: dict[str, Any] = {}
    for payload in case["questions"]:
        question_id = payload["question_id"]
        question = next(question for question in framework.questions if question.id == question_id)
        previous = result["derivation"].get(question_id) or {}
        ai_result = answers.get((case["puid"], question_id))
        if ai_result is None:
            summary["unanswered_by_batch"] += 1
            continue
        answer_id = ai_result["answer_id"]
        answer = question.answer_by_id(answer_id)
        status = "ai_abstained" if answer.abstention else "ai_interpreted"
        if answer.abstention:
            summary["abstentions"] += 1
        else:
            summary["accepted_answers"] += 1
        result["answers"][question_id] = answer_id
        result["scoring_answers"][question_id] = {
            "answer_id": answer_id,
            "derivation_status": status,
            "missing": answer.abstention and previous.get("status") == "missing_evidence",
        }
        result["derivation"][question_id] = {
            "answer_id": answer_id,
            "status": status,
            "previous_status": previous.get("status"),
            "previous_answer_id": previous.get("answer_id"),
            "evidence_fields": list(question.evidence_fields),
            "evidence_claims": ai_result["cited_evidence"],
            "ai": {key: value for key, value in ai_result.items() if key != "cited_evidence"},
        }
        audit[question_id] = {
            **ai_result,
            "previous_status": previous.get("status"),
            "previous_answer_id": previous.get("answer_id"),
        }
    result["ai_summary"] = summary
    result["ai_audit"] = audit
    return result


def apply_batched_fill_gaps(
    provider: AIProvider,
    reader,
    framework,
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    *,
    user_question: str,
    max_evidence_items: int = 20,
    max_puids_per_call: int = 8,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Interpret fill-gaps for many human-matched PUIDs in bounded batch calls.

    Deterministic assessments are already present in ``assessments``. AI receives
    several PUIDs together, keyed by PUID and question ID, so human family/name
    queries do not create one network call per unresolved question per PUID.
    """
    if len(candidates) != len(assessments):
        raise ValueError("Batch AI candidate/assessment counts must match.")
    batch_size = max(1, int(max_puids_per_call))
    cases = [
        _prepare_case(
            reader,
            framework,
            candidate,
            request,
            max_evidence_items=max_evidence_items,
        )
        for candidate in candidates
    ]
    active_cases = [case for case in cases if case["questions"]]
    all_answers: dict[tuple[str, str], dict[str, Any]] = {}
    validation_errors: list[str] = []
    call_count = 0
    failed_error: str | None = None

    for start in range(0, len(active_cases), batch_size):
        chunk = active_cases[start : start + batch_size]
        call_count += 1
        if progress:
            progress(
                f"AI fill-gaps batch {call_count}: {len(chunk)} PUID(s), "
                f"{sum(len(case['questions']) for case in chunk)} unresolved question(s)"
            )
        payload = _request_payload(user_question, chunk, framework)
        request_obj = AIRequest(
            messages=(
                AIMessage("system", BATCH_RISK_SYSTEM_PROMPT),
                AIMessage(
                    "user",
                    "Answer the preservation-risk framework questions for the matched PUIDs below. "
                    "Return one answer for each supplied PUID/question pair.\n\n"
                    + json.dumps(payload, indent=2, sort_keys=True, default=str),
                ),
            ),
            response_schema=_response_schema(),
            response_schema_name="batched_preservation_risk_answers",
            temperature=0.0,
        )
        try:
            response = provider.generate(request_obj)
        except AIProviderError as exc:
            failed_error = str(exc)
            break
        validated, errors = _validate_answers(response, chunk, framework)
        all_answers.update(validated)
        validation_errors.extend(errors)

    for case, assessment in zip(cases, assessments):
        merged = _merge_case(case, all_answers, framework)
        analysis = score_answers(framework, merged.get("scoring_answers") or merged["answers"])
        status = "ok"
        reason = None
        if failed_error and not any(key[0] == case["puid"] for key in all_answers):
            status = "error_deterministic_retained"
            reason = "batch_provider_error"
        assessment["ai_risk_assessment"] = {
            "status": status,
            "ai_mode": "fill-gaps",
            "provider": provider.describe(),
            "evidence_hash": case["evidence_hash"],
            "criterion_claims_used": case["criterion_claims_used"],
            "ai_source_evidence_items": case["ai_source_evidence_items"],
            "ai_source_records_used": case["ai_source_records_used"],
            "ai_format_context": case["format"],
            "deterministic_analysis": case["deterministic_analysis"],
            "analysis": analysis,
            "derived_answers": merged,
            "batch": {
                "user_question": user_question,
                "matched_puid_count": len(candidates),
                "max_puids_per_call": batch_size,
                "provider_call_count": call_count,
                "validation_errors": validation_errors,
            },
            "authority_boundary": (
                "Deterministic answers and scores use approved criterion evidence only. Batched AI fill-gaps may "
                "interpret bounded evidence for unresolved questions and is keyed to the supplied PUID; it cannot "
                "replace deterministically resolved answers, change framework governance, or create policy."
            ),
        }
        if failed_error:
            assessment["ai_risk_assessment"]["error"] = failed_error
        if reason:
            assessment["ai_risk_assessment"]["reason"] = reason

    return {
        "provider_call_count": call_count,
        "matched_puid_count": len(candidates),
        "active_puid_count": len(active_cases),
        "failed_error": failed_error,
        "validation_errors": validation_errors,
    }
