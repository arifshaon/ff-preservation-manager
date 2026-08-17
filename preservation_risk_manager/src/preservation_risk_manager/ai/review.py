from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.ai.base import AIProvider, AIProviderError
from preservation_risk_manager.ai.risk_analysis import interpret_question_with_ai
from preservation_risk_manager.frameworks import RiskFramework


_EVIDENCE_SECTIONS = (
    "global_evidence",
    "institution_evidence",
    "migration_pathway_evidence",
    "local_migration_readiness",
    "ai_source_evidence",
)

# Review-all is intended to validate deterministic mappings independently. Only
# raw/source-facing evidence and provenance are exposed to the model. In
# particular, normalized values, controlled answers, mapping IDs/versions,
# storage keys, and mapping rationale are deliberately excluded.
_RAW_REVIEW_EVIDENCE_KEYS = (
    "canonical_id",
    "criterion_id",
    "evidence_field",
    "evidence_kind",
    "native_field",
    "source_id",
    "source_type",
    "source_record_id",
    "source_name",
    "source_field",
    "source_value",
    "native_vocabulary",
    "institution_id",
    "source_independence",
    "evidence_section",
    "link_basis",
    "observed_at",
    "current",
    "source_url",
    "url",
    "uri",
    "source_title",
    "title",
    "raw_value",
    "raw_text",
    "text",
    "description",
    "note",
    "notes",
)

_RAW_PAYLOAD_KEYS = {
    "source_value",
    "raw_value",
    "raw_text",
    "text",
    "description",
    "note",
    "notes",
}

_AUDIT_EVIDENCE_KEYS = _RAW_REVIEW_EVIDENCE_KEYS


def _raw_review_item(item: dict[str, Any]) -> dict[str, Any] | None:
    sanitized = {
        key: deepcopy(item[key])
        for key in _RAW_REVIEW_EVIDENCE_KEYS
        if key in item and item[key] is not None
    }
    if not any(key in sanitized for key in _RAW_PAYLOAD_KEYS):
        return None
    return sanitized


def _raw_review_evidence_pack(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Return the evidence-only view allowed to reach independent AI review.

    The format identity, scope, institution, and question-matching criterion IDs
    are retained, but deterministic normalization/mapping outputs are stripped.
    Evidence items without a surviving raw payload are omitted rather than
    allowing the model to infer from a normalized stub. Linked source-native
    evidence keeps only its source payload and provenance/link basis.
    """
    sanitized: dict[str, Any] = {
        "scope": evidence_pack.get("scope", "global"),
        "format": deepcopy(evidence_pack.get("format") or {}),
    }
    if evidence_pack.get("institution_id") is not None:
        sanitized["institution_id"] = evidence_pack.get("institution_id")

    for section in _EVIDENCE_SECTIONS:
        value = evidence_pack.get(section) or []
        items = [value] if isinstance(value, dict) else list(value)
        sanitized_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_item = _raw_review_item(item)
            if raw_item is not None:
                sanitized_items.append(raw_item)
        sanitized[section] = sanitized_items
    return sanitized


def _compact_cited_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: item[key] for key in _AUDIT_EVIDENCE_KEYS if key in item and item[key] is not None}
        for item in items
        if isinstance(item, dict)
    ]


def review_answers_with_ai(
    provider: AIProvider,
    framework: RiskFramework,
    evidence_pack: dict[str, Any],
    deterministic_answer_document: dict[str, Any],
    *,
    max_evidence_items: int = 20,
) -> dict[str, Any]:
    """Independently review all framework questions without changing scoring answers.

    This mode is for calibration and audit. The AI receives only raw/source-facing
    evidence plus bounded provenance selected by the framework question's
    declared evidence fields. It does not receive normalized criterion values,
    deterministic answers/status, mapping rules, score, band, or deterministic
    evidence preference before responding. Comparison happens only after the AI
    answer has been validated. Deterministic scoring inputs remain unchanged even
    when the AI disagrees.
    """
    result = deepcopy(deterministic_answer_document)
    derivation = result.setdefault("derivation", {})
    review_evidence_pack = _raw_review_evidence_pack(evidence_pack)

    summary = {
        "mode": "review_all",
        "evidence_view": "raw_source_only",
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
                review_evidence_pack,
                deterministic_result,
                max_evidence_items=max_evidence_items,
                include_deterministic_context=False,
                prefer_deterministic_evidence=False,
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

        audit_ai_result = {
            key: value
            for key, value in ai_result.items()
            if key != "cited_evidence"
        }
        audit[question.id] = {
            **audit_ai_result,
            "cited_evidence": _compact_cited_evidence(ai_result.get("cited_evidence") or []),
            "comparison": comparison,
            "agreement": agreement,
            "deterministic_answer_id": deterministic_answer_id,
            "deterministic_status": deterministic_status,
        }

    result["derivation_method"] = "deterministic_with_independent_raw_evidence_ai_review"
    result["ai_summary"] = summary
    result["ai_audit"] = audit
    return result
