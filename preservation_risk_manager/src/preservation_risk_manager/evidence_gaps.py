from __future__ import annotations

import json
from typing import Any

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


_VALUE_KEYS = ("value", "status", "level", "assessment", "rating", "state")


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
    return {
        "format_id": str(format_id) if format_id is not None else None,
        "label": str(label) if label is not None else None,
        "extensions": [str(value) for value in _as_list(format_doc.get("extensions") or format_doc.get("file_extensions"))],
        "mime_types": [str(value) for value in _as_list(format_doc.get("mime_types") or format_doc.get("mime_type"))],
        "puids": [str(value) for value in _as_list(format_doc.get("puids"))],
        "loc_ids": [str(value) for value in _as_list(format_doc.get("loc_ids"))],
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
        "critical": question.critical,
        "derivation_status": status,
        "gap_reason": gap_reason,
        "expected_evidence_fields": list(question.evidence_fields),
        "matched_claim_count": len(matched_claims),
        "matched_criterion_ids": criterion_ids,
        "matched_values": values,
    }


def diagnose_format_evidence_gaps(
    reader: RegistryReader,
    framework: RiskFramework,
    format_doc: dict[str, Any],
    *,
    institution_id: str | None = None,
) -> dict[str, Any]:
    """Diagnose why framework questions cannot be deterministically answered.

    The diagnosis is derived only from the same explicit criterion claims and
    framework declarations used by deterministic scoring. It never uses AI or
    general file-format knowledge.
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
    matched_keys: set[str] = set()
    unmapped_keys: set[str] = set()
    for question in framework.questions:
        derivation = answers["derivation"].get(question.id) or {}
        for claim in derivation.get("evidence_claims") or []:
            if isinstance(claim, dict):
                matched_keys.add(_claim_key(claim))
        gap = _question_gap(question, derivation)
        if gap is None:
            continue
        gaps.append(gap)
        if gap["gap_reason"] == "claims_exist_but_do_not_map":
            for claim in derivation.get("evidence_claims") or []:
                if isinstance(claim, dict):
                    unmapped_keys.add(_claim_key(claim))

    reason_counts: dict[str, int] = {}
    for gap in gaps:
        reason = str(gap["gap_reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

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
        "criterion_claims_available": len(claims),
        "matched_claims_for_framework": len(matched_keys),
        "unmapped_claims_for_framework": len(unmapped_keys),
        "unrelated_claims": max(0, len(claims) - len(matched_keys)),
        "gap_classification": classification,
        "gap_count": len(gaps),
        "gap_reason_counts": reason_counts,
        "missing_questions": gaps,
        "evidence_hash": evidence_hash(pack),
    }


def summarize_evidence_gaps(rows: list[dict[str, Any]], *, candidate_count: int) -> dict[str, Any]:
    question_reason_counts: dict[str, int] = {}
    classification_counts: dict[str, int] = {}
    for row in rows:
        classification = str(row.get("gap_classification") or "unknown")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        for reason, count in (row.get("gap_reason_counts") or {}).items():
            question_reason_counts[str(reason)] = question_reason_counts.get(str(reason), 0) + int(count)
    return {
        "candidate_count": candidate_count,
        "formats_with_gaps": len(rows),
        "fully_covered_formats": max(0, candidate_count - len(rows)),
        "format_gap_classification_counts": classification_counts,
        "question_gap_reason_counts": question_reason_counts,
    }
