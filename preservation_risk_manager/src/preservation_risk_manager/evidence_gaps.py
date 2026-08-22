from __future__ import annotations

from collections import Counter
import json
from typing import Any

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


_VALUE_KEYS = ("value", "status", "level", "assessment", "rating", "state")
_LOCAL_DOMAIN = "local_institutional_feasibility"
_CONTENT_SPECIFIC_DOMAIN = "essential_characteristics"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _format_identity(format_doc: dict[str, Any]) -> dict[str, Any]:
    format_id = format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id")
    label = (
        format_doc.get("preferred_name")
        or format_doc.get("format_name")
        or format_doc.get("name")
        or format_doc.get("label")
        or format_doc.get("display_name")
    )
    identifiers = format_doc.get("identifiers") or {}
    if not isinstance(identifiers, dict):
        identifiers = {}
    return {
        "format_id": str(format_id) if format_id is not None else None,
        "label": str(label) if label is not None else None,
        "extensions": [
            str(value)
            for value in _as_list(
                format_doc.get("extensions")
                or format_doc.get("file_extensions")
                or identifiers.get("extension")
            )
        ],
        "mime_types": [
            str(value)
            for value in _as_list(
                format_doc.get("mime_types")
                or format_doc.get("mime_type")
                or identifiers.get("mime")
            )
        ],
        "puids": [
            str(value)
            for value in _as_list(format_doc.get("puids") or identifiers.get("puid"))
        ],
        "loc_ids": [
            str(value)
            for value in _as_list(format_doc.get("loc_ids") or identifiers.get("loc"))
        ],
    }


def _claim_key(claim: dict[str, Any]) -> str:
    for key in ("claim_id", "source_claim_id", "_storage_key"):
        value = claim.get(key)
        if value is not None:
            return f"{key}:{value}"
    return json.dumps(claim, sort_keys=True, default=str)


def _claim_value(claim: dict[str, Any]) -> Any:
    for key in _VALUE_KEYS:
        if key in claim and claim[key] is not None:
            return claim[key]
    return None


def _work_type_for_gap(question: Any, gap_reason: str) -> str:
    """Classify the kind of work needed without inferring any preservation fact.

    The active MongoDB registry is treated as locked input. This classification
    describes how an unresolved framework question should be investigated; it is
    not permission to add, remap, or rewrite registry evidence.
    """
    if gap_reason == "claims_exist_but_do_not_map":
        return "deterministic_mapping_review"

    domain_id = str(getattr(question, "domain_id", None) or "")
    if domain_id == _LOCAL_DOMAIN:
        return "institution_evidence_required"
    if domain_id == _CONTENT_SPECIFIC_DOMAIN or getattr(question, "applicability", ()):
        return "content_specific_assessment_required"
    if domain_id:
        return "automated_evidence_research_required"
    return "source_evidence_required"


def _question_gap(question: Any, derivation: dict[str, Any]) -> dict[str, Any] | None:
    status = str(derivation.get("status") or "")
    if status in {"derived", "derived_conflict_conservative"}:
        return None

    matched_claims = [claim for claim in derivation.get("evidence_claims") or [] if isinstance(claim, dict)]
    if status == "missing_evidence":
        gap_reason = "no_matching_evidence"
    elif status == "unknown" and matched_claims:
        gap_reason = "claims_exist_but_do_not_map"
    else:
        gap_reason = "unresolved"

    criterion_ids = sorted({str(claim.get("criterion_id")) for claim in matched_claims if claim.get("criterion_id")})
    values = []
    for claim in matched_claims:
        value = _claim_value(claim)
        if value is not None and value not in values:
            values.append(value)

    return {
        "question_id": question.id,
        "label": question.label,
        "domain_id": getattr(question, "domain_id", None),
        "domain_label": getattr(question, "domain_label", None),
        "applicability": list(getattr(question, "applicability", ()) or ()),
        "critical": question.critical,
        "derivation_status": status,
        "gap_reason": gap_reason,
        "work_type": _work_type_for_gap(question, gap_reason),
        "expected_evidence_fields": list(question.evidence_fields),
        "matched_claim_count": len(matched_claims),
        "matched_criterion_ids": criterion_ids,
        "matched_values": values,
    }


def _request_applicability(
    question: Any,
    *,
    institution_id: str | None,
    content_type: str | None,
) -> str:
    """Describe whether a framework question is actionable in this request.

    This does not change the framework itself. It only prevents a global request
    from treating institution-only questions as missing global evidence, and
    prevents an unspecified content type from treating every mutually exclusive
    fidelity question as immediately assessable.
    """
    domain_id = str(getattr(question, "domain_id", None) or "")
    if domain_id == _LOCAL_DOMAIN and not institution_id:
        return "deferred_until_institution_scope"

    applicability = tuple(str(value).strip().lower() for value in (getattr(question, "applicability", ()) or ()) if str(value).strip())
    if applicability:
        if not content_type:
            return "deferred_until_content_type"
        normalized_content = str(content_type).strip().lower().replace("-", "_").replace(" ", "_")
        normalized_applicability = {
            value.replace("-", "_").replace(" ", "_")
            for value in applicability
        }
        if "all" not in normalized_applicability and normalized_content not in normalized_applicability:
            return "not_applicable_to_content_type"

    return "applicable"


def _deferred_question(question: Any, derivation: dict[str, Any], request_applicability: str) -> dict[str, Any]:
    gap = _question_gap(question, derivation)
    base = gap or {
        "question_id": question.id,
        "label": question.label,
        "domain_id": getattr(question, "domain_id", None),
        "domain_label": getattr(question, "domain_label", None),
        "applicability": list(getattr(question, "applicability", ()) or ()),
        "critical": question.critical,
        "derivation_status": str(derivation.get("status") or ""),
        "expected_evidence_fields": list(question.evidence_fields),
        "matched_claim_count": 0,
        "matched_criterion_ids": [],
        "matched_values": [],
    }
    base["request_applicability"] = request_applicability
    return base


def _current_context_rows(
    reader: RegistryReader,
    collection: str,
    canonical_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for canonical_id in canonical_ids:
        for row in reader.query(collection, {"canonical_id": canonical_id}):
            if row.get("current") is False:
                continue
            key = _claim_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _non_scoring_context(reader: RegistryReader, format_doc: dict[str, Any]) -> dict[str, Any]:
    """Summarize locked registry context that is intentionally not question evidence."""
    canonical_ids = reader.criterion_claim_canonical_ids(format_doc)
    risk_rows = _current_context_rows(reader, "risk_assessment_claims", canonical_ids)
    relationship_rows = _current_context_rows(reader, "source_relationship_claims", canonical_ids)

    risk_sources = Counter(str(row.get("source_id") or "unknown") for row in risk_rows)
    risk_scopes = Counter(str(row.get("scope_type") or "unknown") for row in risk_rows)
    relationship_sources = Counter(str(row.get("source_id") or "unknown") for row in relationship_rows)
    relationship_types = Counter(str(row.get("relationship") or "unknown") for row in relationship_rows)

    return {
        "canonical_ids_checked": canonical_ids,
        "external_risk_assessment_count": len(risk_rows),
        "external_risk_sources": dict(sorted(risk_sources.items())),
        "external_risk_scope_types": dict(sorted(risk_scopes.items())),
        "relationship_claim_count": len(relationship_rows),
        "relationship_sources": dict(sorted(relationship_sources.items())),
        "relationship_types": dict(sorted(relationship_types.items())),
        "scoring_effect": "context_only",
    }


def diagnose_format_evidence_gaps(
    reader: RegistryReader,
    framework: RiskFramework,
    format_doc: dict[str, Any],
    *,
    institution_id: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Diagnose why framework questions cannot be deterministically answered.

    The diagnosis uses the same governed criterion claims and framework
    declarations as deterministic scoring. The registry is treated as locked
    read-only input. NARA/DPC risk assessments and relationship claims are
    summarized separately as non-scoring context and never promoted to answers.

    ``evidence_completeness`` remains the full-framework scoring metric for
    auditability. ``applicable_evidence_completeness`` is request-sensitive and
    excludes questions deferred until institution scope or content type is known.
    """
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(
        format_doc,
        institution_id=institution_id,
        criterion_claims=claims,
    )
    answers = derive_answers(framework, pack)
    analysis = score_answers(framework, answers.get("scoring_answers") or answers["answers"])

    gaps: list[dict[str, Any]] = []
    deferred_questions: list[dict[str, Any]] = []
    excluded_questions: list[dict[str, Any]] = []
    matched_keys: set[str] = set()
    unmapped_keys: set[str] = set()
    applicable_question_count = 0
    applicable_answered_count = 0

    for question in framework.questions:
        derivation = answers["derivation"].get(question.id) or {}
        request_applicability = _request_applicability(
            question,
            institution_id=institution_id,
            content_type=content_type,
        )

        if request_applicability == "not_applicable_to_content_type":
            excluded_questions.append(_deferred_question(question, derivation, request_applicability))
            continue
        if request_applicability != "applicable":
            deferred_questions.append(_deferred_question(question, derivation, request_applicability))
            continue

        applicable_question_count += 1
        for claim in derivation.get("evidence_claims") or []:
            if isinstance(claim, dict):
                matched_keys.add(_claim_key(claim))

        gap = _question_gap(question, derivation)
        if gap is None:
            applicable_answered_count += 1
            continue
        gap["request_applicability"] = "applicable"
        gaps.append(gap)
        if gap["gap_reason"] == "claims_exist_but_do_not_map":
            for claim in derivation.get("evidence_claims") or []:
                if isinstance(claim, dict):
                    unmapped_keys.add(_claim_key(claim))

    reason_counts: dict[str, int] = {}
    work_type_counts: dict[str, int] = {}
    deferred_reason_counts: dict[str, int] = {}
    for gap in gaps:
        reason = str(gap["gap_reason"])
        work_type = str(gap["work_type"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        work_type_counts[work_type] = work_type_counts.get(work_type, 0) + 1
    for question in deferred_questions:
        reason = str(question.get("request_applicability") or "deferred")
        deferred_reason_counts[reason] = deferred_reason_counts.get(reason, 0) + 1

    if not gaps:
        classification = "none"
    elif unmapped_keys and reason_counts.get("no_matching_evidence"):
        classification = "mixed_mapping_and_evidence_gaps"
    elif unmapped_keys:
        classification = "claims_exist_but_do_not_map"
    elif not claims:
        classification = "no_evidence"
    elif not matched_keys:
        classification = "claims_exist_but_not_for_framework"
    else:
        classification = "missing_matching_evidence"

    return {
        "format": _format_identity(format_doc),
        "analysis_status": analysis.get("analysis_status"),
        "risk_band": analysis.get("analysed_band"),
        "band_suppressed_reason": analysis.get("band_suppressed_reason"),
        "evidence_completeness": analysis.get("evidence_completeness"),
        "applicable_evidence_completeness": (
            applicable_answered_count / applicable_question_count
            if applicable_question_count
            else 0.0
        ),
        "applicable_question_count": applicable_question_count,
        "applicable_answered_question_count": applicable_answered_count,
        "criterion_claims_available": len(claims),
        "matched_claims_for_framework": len(matched_keys),
        "unmapped_claims_for_framework": len(unmapped_keys),
        "unrelated_claims": max(0, len(claims) - len(matched_keys)),
        "gap_classification": classification,
        "gap_count": len(gaps),
        "total_unresolved_question_count": len(gaps) + len(deferred_questions),
        "deferred_question_count": len(deferred_questions),
        "excluded_question_count": len(excluded_questions),
        "gap_reason_counts": reason_counts,
        "work_type_counts": work_type_counts,
        "deferred_reason_counts": deferred_reason_counts,
        "missing_questions": gaps,
        "deferred_questions": deferred_questions,
        "excluded_questions": excluded_questions,
        "request_context": {
            "scope": "institution" if institution_id else "global",
            "institution_id": institution_id,
            "content_type": content_type,
        },
        "non_scoring_registry_context": _non_scoring_context(reader, format_doc),
        "evidence_hash": evidence_hash(pack),
    }


def summarize_evidence_gaps(rows: list[dict[str, Any]], *, candidate_count: int) -> dict[str, Any]:
    question_reason_counts: dict[str, int] = {}
    work_type_counts: dict[str, int] = {}
    deferred_reason_counts: dict[str, int] = {}
    classification_counts: dict[str, int] = {}
    for row in rows:
        classification = str(row.get("gap_classification") or "unknown")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        for reason, count in (row.get("gap_reason_counts") or {}).items():
            question_reason_counts[str(reason)] = question_reason_counts.get(str(reason), 0) + int(count)
        for work_type, count in (row.get("work_type_counts") or {}).items():
            work_type_counts[str(work_type)] = work_type_counts.get(str(work_type), 0) + int(count)
        for reason, count in (row.get("deferred_reason_counts") or {}).items():
            deferred_reason_counts[str(reason)] = deferred_reason_counts.get(str(reason), 0) + int(count)
    return {
        "candidate_count": candidate_count,
        "formats_with_gaps": len(rows),
        "fully_covered_formats": max(0, candidate_count - len(rows)),
        "format_gap_classification_counts": classification_counts,
        "question_gap_reason_counts": question_reason_counts,
        "question_work_type_counts": work_type_counts,
        "deferred_question_reason_counts": deferred_reason_counts,
    }
