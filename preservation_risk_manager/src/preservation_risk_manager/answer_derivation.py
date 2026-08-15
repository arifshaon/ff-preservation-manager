from __future__ import annotations

from typing import Any

from preservation_risk_manager.frameworks import Question, RiskFramework


DERIVATION_VALUE_MAP: dict[str, dict[str, str]] = {
    "sustainability.disclosure": {
        "openly_documented": "public_specification",
        "open_documentation": "public_specification",
        "public_specification": "public_specification",
        "public_specification_available": "public_specification",
        "limited": "limited_or_unclear_specification",
        "limited_documentation": "limited_or_unclear_specification",
        "unclear": "limited_or_unclear_specification",
        "restricted": "limited_or_unclear_specification",
    },
    "sustainability.adoption": {
        "widely_adopted": "widely_adopted",
        "active": "widely_adopted",
        "actively_used": "widely_adopted",
        "common": "widely_adopted",
        "mainstream": "widely_adopted",
        "niche": "niche_or_declining",
        "declining": "niche_or_declining",
        "domain_specific": "niche_or_declining",
        "niche_or_declining": "niche_or_declining",
    },
    "sustainability.external_dependencies": {
        "none": "no_special_dependency",
        "no_special_dependency": "no_special_dependency",
        "common_tooling": "no_special_dependency",
        "standard_tooling": "no_special_dependency",
        "specialist": "specialist_dependency",
        "specialist_dependency": "specialist_dependency",
        "proprietary_dependency": "specialist_dependency",
        "runtime_dependency": "specialist_dependency",
    },
    "technical.container_complexity": {
        "simple": "no_special_dependency",
        "standard": "no_special_dependency",
        "common_tooling": "no_special_dependency",
        "complex": "specialist_dependency",
        "specialist": "specialist_dependency",
        "specialist_dependency": "specialist_dependency",
    },
}

_EVIDENCE_SECTIONS = (
    "global_evidence",
    "institution_evidence",
    "migration_pathway_evidence",
    "local_migration_readiness",
)
_VALUE_KEYS = ("value", "status", "level", "assessment", "rating", "state")
_EXPLICIT_ANSWER_KEYS = ("answer_id", "controlled_answer_id", "framework_answer_id")


def _normalise(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _allowed_answers(question: Question) -> set[str]:
    return {answer.id for answer in question.answers}


def _answer_points(question: Question, answer_id: str) -> float:
    return question.answer_by_id(answer_id).points


def evidence_items(evidence_pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all evidence items in stable section order."""
    items: list[dict[str, Any]] = []
    for section in _EVIDENCE_SECTIONS:
        section_value = evidence_pack.get(section) or []
        if isinstance(section_value, dict):
            section_items = [section_value]
        else:
            section_items = list(section_value)
        for item in section_items:
            if isinstance(item, dict):
                stored = dict(item)
                stored.setdefault("evidence_section", section)
                items.append(stored)
    return items


def _claim_matches_field(claim: dict[str, Any], evidence_field: str) -> bool:
    fields = (
        claim.get("criterion_id"),
        claim.get("field"),
        claim.get("evidence_field"),
        claim.get("path"),
    )
    return evidence_field in {str(field) for field in fields if field is not None}


def _claim_value(claim: dict[str, Any]) -> str | None:
    for key in _VALUE_KEYS:
        if key in claim and claim[key] is not None:
            return _normalise(claim[key])
    return None


def _explicit_answer_id(claim: dict[str, Any], allowed: set[str]) -> str | None:
    for key in _EXPLICIT_ANSWER_KEYS:
        value = claim.get(key)
        if value is not None and str(value) in allowed:
            return str(value)
    return None


def _answer_from_claim(question: Question, evidence_field: str, claim: dict[str, Any]) -> str | None:
    allowed = _allowed_answers(question)
    explicit = _explicit_answer_id(claim, allowed)
    if explicit:
        return explicit
    value = _claim_value(claim)
    if not value:
        return None
    answer_id = DERIVATION_VALUE_MAP.get(evidence_field, {}).get(value)
    if answer_id in allowed:
        return answer_id
    return None


def _derive_question_answer(question: Question, claims: list[dict[str, Any]], *, unknown_answer_id: str) -> dict[str, Any]:
    matched_claims: list[dict[str, Any]] = []
    candidates: list[tuple[str, dict[str, Any], str]] = []
    for evidence_field in question.evidence_fields:
        for claim in claims:
            if not _claim_matches_field(claim, evidence_field):
                continue
            matched_claims.append(claim)
            answer_id = _answer_from_claim(question, evidence_field, claim)
            if answer_id:
                candidates.append((answer_id, claim, evidence_field))

    if not candidates:
        return {
            "answer_id": unknown_answer_id,
            "status": "unknown" if matched_claims else "missing_evidence",
            "evidence_fields": list(question.evidence_fields),
            "evidence_claims": matched_claims,
        }

    answer_ids = {candidate[0] for candidate in candidates}
    if len(answer_ids) == 1:
        answer_id = candidates[0][0]
        return {
            "answer_id": answer_id,
            "status": "derived",
            "evidence_fields": list(question.evidence_fields),
            "evidence_claims": [candidate[1] for candidate in candidates],
        }

    # Deterministic preservation-safe behaviour: when explicit evidence maps to
    # conflicting controlled answers, choose the highest-point answer and expose
    # the conflict in derivation metadata instead of silently ignoring it.
    answer_id = max(answer_ids, key=lambda item: (_answer_points(question, item), item))
    return {
        "answer_id": answer_id,
        "status": "derived_conflict_conservative",
        "evidence_fields": list(question.evidence_fields),
        "evidence_claims": [candidate[1] for candidate in candidates],
        "conflicting_answer_ids": sorted(answer_ids),
    }


def derive_answers(framework: RiskFramework, evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Derive controlled framework answer IDs from explicit registry evidence.

    This function does not infer from format names, extensions, hazard bands, or
    general knowledge. It only uses evidence claims whose criterion/field matches
    a framework question's declared evidence_fields.
    """
    claims = evidence_items(evidence_pack)
    answers: dict[str, str] = {}
    derivation: dict[str, dict[str, Any]] = {}
    for question in framework.questions:
        result = _derive_question_answer(
            question,
            claims,
            unknown_answer_id=framework.unknown_answer_id,
        )
        answers[question.id] = result["answer_id"]
        derivation[question.id] = result
    return {
        "answers": answers,
        "derivation": derivation,
        "derivation_method": "explicit_criterion_evidence",
    }
