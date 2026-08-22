from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


_PRIORITY_RANK = {"P1": 3, "P2": 2, "P3": 1}


def _priority_for_gap(gap: dict[str, Any]) -> str:
    """Assign a deterministic remediation priority.

    Critical framework questions are always P1. For non-critical questions,
    bounded mapping, institution-input, and content-specific work are P2.
    Open-ended external/source research remains P3.
    """
    if bool(gap.get("critical")):
        return "P1"
    if gap.get("work_type") in {
        "deterministic_mapping_review",
        "institution_evidence_required",
        "content_specific_assessment_required",
    }:
        return "P2"
    return "P3"


def _action_for_gap(gap: dict[str, Any]) -> tuple[str, str]:
    work_type = str(gap.get("work_type") or "")
    gap_reason = str(gap.get("gap_reason") or "unresolved")

    if work_type == "deterministic_mapping_review" or gap_reason == "claims_exist_but_do_not_map":
        return "mapping_rule_needed", "matched_claim_value_not_in_deterministic_mapping"
    if work_type == "institution_evidence_required":
        return "institution_evidence_needed", "question_requires_institution_scoped_evidence"
    if work_type == "content_specific_assessment_required":
        return "content_specific_assessment_needed", "question_requires_content_specific_significant_properties"
    if work_type == "automated_evidence_research_required":
        return "automated_evidence_research", "locked_registry_has_no_deterministic_question_evidence"
    if work_type == "source_evidence_required" or gap_reason == "no_matching_evidence":
        return "source_evidence_needed", "no_claim_matches_framework_evidence_field"
    return "manual_review_needed", "unresolved_derivation_gap"


def _item_for_gap(gap: dict[str, Any]) -> dict[str, Any]:
    action_type, reason_code = _action_for_gap(gap)
    return {
        "priority": _priority_for_gap(gap),
        "action_type": action_type,
        "reason_code": reason_code,
        "work_type": gap.get("work_type"),
        "question_id": gap.get("question_id"),
        "question_label": gap.get("label"),
        "domain_id": gap.get("domain_id"),
        "domain_label": gap.get("domain_label"),
        "applicability": list(gap.get("applicability") or []),
        "critical": bool(gap.get("critical")),
        "target_evidence_fields": list(gap.get("expected_evidence_fields") or []),
        "matched_claim_count": int(gap.get("matched_claim_count") or 0),
        "matched_criterion_ids": list(gap.get("matched_criterion_ids") or []),
        "observed_values": list(gap.get("matched_values") or []),
    }


def plan_format_evidence_remediation(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Convert one deterministic evidence-gap diagnosis into an action queue.

    The planner treats the registry as locked input. Its actions describe work in
    the preservation-risk assessment layer: evidence research, institution input,
    content-specific assessment, or bounded mapping review. It never instructs a
    caller to rewrite registry source data merely because a framework answer is
    unknown.
    """
    items = [
        _item_for_gap(gap)
        for gap in diagnostic.get("missing_questions") or []
        if isinstance(gap, dict)
    ]

    # When claims exist but none match any field in the active framework, add a
    # bounded alignment review before assuming entirely new evidence is needed.
    # This does not assert that the existing claims are sufficient or authorize a
    # registry-builder mapping change.
    if (
        diagnostic.get("gap_classification") == "claims_exist_but_not_for_framework"
        and int(diagnostic.get("criterion_claims_available") or 0) > 0
    ):
        has_critical_gap = any(bool(gap.get("critical")) for gap in diagnostic.get("missing_questions") or [])
        items.append({
            "priority": "P1" if has_critical_gap else "P2",
            "action_type": "framework_alignment_review",
            "reason_code": "claims_available_but_none_match_active_framework_fields",
            "work_type": "deterministic_mapping_review",
            "question_id": None,
            "question_label": None,
            "domain_id": None,
            "domain_label": None,
            "applicability": [],
            "critical": has_critical_gap,
            "target_evidence_fields": [],
            "matched_claim_count": 0,
            "matched_criterion_ids": [],
            "observed_values": [],
        })

    items.sort(
        key=lambda item: (
            -_PRIORITY_RANK.get(str(item.get("priority")), 0),
            str(item.get("action_type") or ""),
            str(item.get("question_id") or ""),
        )
    )
    action_counts = Counter(str(item["action_type"]) for item in items)
    priority_counts = Counter(str(item["priority"]) for item in items)
    work_type_counts = Counter(str(item.get("work_type") or "unknown") for item in items)

    return {
        "format": deepcopy(diagnostic.get("format") or {}),
        "analysis_status": diagnostic.get("analysis_status"),
        "risk_band": diagnostic.get("risk_band"),
        "band_suppressed_reason": diagnostic.get("band_suppressed_reason"),
        "evidence_completeness": diagnostic.get("evidence_completeness"),
        "gap_classification": diagnostic.get("gap_classification"),
        "criterion_claims_available": diagnostic.get("criterion_claims_available"),
        "non_scoring_registry_context": deepcopy(diagnostic.get("non_scoring_registry_context") or {}),
        "remediation_item_count": len(items),
        "priority_counts": dict(sorted(priority_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "work_type_counts": dict(sorted(work_type_counts.items())),
        "remediation_items": items,
        "evidence_hash": diagnostic.get("evidence_hash"),
    }


def summarize_evidence_remediation(rows: list[dict[str, Any]], *, candidate_count: int) -> dict[str, Any]:
    action_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    work_type_counts: Counter[str] = Counter()
    question_action_counts: dict[str, Counter[str]] = {}

    for row in rows:
        for item in row.get("remediation_items") or []:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "unknown")
            priority = str(item.get("priority") or "unknown")
            work_type = str(item.get("work_type") or "unknown")
            action_counts[action_type] += 1
            priority_counts[priority] += 1
            work_type_counts[work_type] += 1
            question_id = item.get("question_id")
            if question_id:
                question_action_counts.setdefault(str(question_id), Counter())[action_type] += 1

    return {
        "candidate_count": candidate_count,
        "formats_requiring_remediation": len(rows),
        "formats_without_remediation": max(0, candidate_count - len(rows)),
        "remediation_item_count": sum(action_counts.values()),
        "action_type_counts": dict(sorted(action_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "work_type_counts": dict(sorted(work_type_counts.items())),
        "question_action_counts": {
            question_id: dict(sorted(counts.items()))
            for question_id, counts in sorted(question_action_counts.items())
        },
    }
