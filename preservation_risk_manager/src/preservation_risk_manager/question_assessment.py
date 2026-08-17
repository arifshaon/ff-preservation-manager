from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.frameworks import Question, RiskFramework
from preservation_risk_manager.scoring import score_answers


def question_catalog_entry(question: Question) -> dict[str, Any]:
    return {
        "question_id": question.id,
        "label": question.label,
        "domain_id": question.domain_id,
        "domain_label": question.domain_label,
        "definition": question.definition,
        "guidance": question.guidance,
        "critical": question.critical,
        "weight": question.weight,
        "evidence_fields": list(question.evidence_fields),
        "applicability": list(question.applicability),
        "aliases": list(question.aliases),
        "answers": [
            {
                "answer_id": answer.id,
                "label": answer.label,
                "points": answer.points,
                "abstention": answer.abstention,
                "definition": answer.definition,
                "guidance": answer.guidance,
            }
            for answer in question.answers
        ],
    }


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def select_questions(
    framework: RiskFramework,
    *,
    domains: Iterable[str] | None = None,
    question_ids: Iterable[str] | None = None,
    content_type: str | None = None,
) -> list[Question]:
    domain_set = {_normalise(value) for value in (domains or []) if str(value).strip()}
    question_set = {str(value).strip() for value in (question_ids or []) if str(value).strip()}
    content = _normalise(content_type) if content_type else None

    selected: list[Question] = []
    for question in framework.questions:
        if domain_set:
            domain_tokens = {
                _normalise(question.domain_id),
                _normalise(question.domain_label),
            }
            domain_tokens.update(_normalise(alias) for alias in question.aliases)
            if not domain_tokens.intersection(domain_set):
                continue
        if question_set and question.id not in question_set:
            continue
        if content and question.applicability:
            applicable = {_normalise(value) for value in question.applicability}
            if "all" not in applicable and content not in applicable:
                continue
        selected.append(question)
    return selected


def list_question_catalog(
    framework: RiskFramework,
    *,
    domains: Iterable[str] | None = None,
    question_ids: Iterable[str] | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    questions = select_questions(
        framework,
        domains=domains,
        question_ids=question_ids,
        content_type=content_type,
    )
    domains_seen: dict[str, str | None] = {}
    for question in questions:
        if question.domain_id:
            domains_seen[question.domain_id] = question.domain_label
    return {
        "framework_id": framework.framework_id,
        "framework_version": framework.version,
        "calibration_status": framework.calibration_status,
        "banding_enabled": framework.banding_enabled,
        "domains": [
            {"domain_id": domain_id, "label": domains_seen[domain_id]}
            for domain_id in sorted(domains_seen)
        ],
        "questions": [question_catalog_entry(question) for question in questions],
        "question_count": len(questions),
    }


def _compact_claim(claim: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "claim_id",
        "source_claim_id",
        "canonical_id",
        "criterion_id",
        "value",
        "source_id",
        "source_type",
        "source_record_id",
        "source_field",
        "institution_id",
        "review_status",
    )
    return {key: deepcopy(claim[key]) for key in keys if key in claim}


def assess_format_questions(
    reader: RegistryReader,
    framework: RiskFramework,
    format_doc: dict[str, Any],
    *,
    domains: Iterable[str] | None = None,
    question_ids: Iterable[str] | None = None,
    content_type: str | None = None,
    institution_id: str | None = None,
) -> dict[str, Any]:
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(format_doc, institution_id=institution_id, criterion_claims=claims)
    answers = derive_answers(framework, pack)
    analysis = score_answers(framework, answers.get("scoring_answers") or answers["answers"])
    selected = select_questions(
        framework,
        domains=domains,
        question_ids=question_ids,
        content_type=content_type,
    )
    score_by_id = {row["question_id"]: row for row in analysis.get("question_results", [])}

    results: list[dict[str, Any]] = []
    for question in selected:
        score_row = score_by_id.get(question.id) or {}
        derivation = answers.get("derivation", {}).get(question.id) or {}
        answer_id = score_row.get("answer_id")
        answer = question.answer_by_id(answer_id) if answer_id else None
        results.append({
            **question_catalog_entry(question),
            "answer_id": answer_id,
            "answer_label": answer.label if answer else None,
            "derivation_status": derivation.get("status"),
            "points": score_row.get("points"),
            "weighted_points": score_row.get("weighted_points"),
            "abstention": score_row.get("abstention"),
            "missing": score_row.get("missing"),
            "matched_evidence_count": len(derivation.get("evidence_claims") or []),
            "evidence": [
                _compact_claim(claim)
                for claim in derivation.get("evidence_claims") or []
                if isinstance(claim, dict)
            ],
        })

    answered = sum(1 for row in results if not row.get("abstention"))
    return {
        "format": {
            "format_id": format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id"),
            "label": format_doc.get("preferred_name") or format_doc.get("format_name") or format_doc.get("name") or format_doc.get("label"),
        },
        "selection": {
            "domains": list(domains or []),
            "question_ids": list(question_ids or []),
            "content_type": content_type,
        },
        "selected_question_count": len(results),
        "answered_question_count": answered,
        "evidence_completeness": answered / len(results) if results else 0.0,
        "questions": results,
        "overall_framework_assessment": {
            "risk_band": analysis.get("analysed_band"),
            "band_suppressed_reason": analysis.get("band_suppressed_reason"),
            "analysis_status": analysis.get("analysis_status"),
            "score": analysis.get("score"),
            "max_score": analysis.get("max_score"),
            "calibration_status": analysis.get("calibration_status"),
            "banding_enabled": analysis.get("banding_enabled"),
        },
        "criterion_claims_available": len(claims),
        "evidence_hash": evidence_hash(pack),
    }
