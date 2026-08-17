from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


_PRIORITY_RANK = {"P1": 3, "P2": 2, "P3": 1}


def _priority_for_gap(gap: dict[str, Any]) -> str:
    """Assign a deterministic remediation priority.

    Critical framework questions are always P1. For non-critical questions,
    existing-but-unmapped evidence is P2 because the registry already contains
    potentially usable evidence and the remaining work is bounded mapping or
    normalization. Missing source evidence is P3.
    """
    if bool(gap.get("critical")):
        return "P1"
    if gap.get("gap_reason") == "claims_exist_but_do_not_map":
        return "P2"
    return "P3"


def _item_for_gap(gap: dict[str, Any]) -> dict[str, Any]:
    gap_reason = str(gap.get("gap_reason") or "unresolved")
    if gap_reason == "claims_exist_but_do_not_map":
        action_type = "mapping_rule_needed"
        reason_code = "matched_claim_value_not_in_deterministic_mapping"
    elif gap_reason == "no_matching_evidence":
        action_type = "source_evidence_needed"
        reason_code = "no_claim_matches_framework_evidence_field"
    else:
        action_type = "manual_review_needed"
        reason_code = "unresolved_derivation_gap"

    return {
        "priority": _priority_for_gap(gap),
        "action_type": action_type,
        "reason_code": reason_code,
        "question_id": gap.get("question_id"),
        "question_label": gap.get("label"),
        "critical": bool(gap.get("critical")),
        "target_evidence_fields": list(gap.get("expected_evidence_fields") or []),
        "matched_claim_count": int(gap.get("matched_claim_count") or 0),
        "matched_criterion_ids": list(gap.get("matched_criterion_ids") or []),
        "observed_values": list(gap.get("matched_values") or []),
    }


def plan_format_evidence_remediation(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Convert one deterministic evidence-gap diagnosis into an action queue.

    This planner does not infer preservation facts. It only translates explicit
    diagnosis states into controlled remediation operation types.
    """
    items = [
        _item_for_gap(gap)
        for gap in diagnostic.get("missing_questions") or []
        if isinstance(gap, dict)
    ]

    # When claims exist but none match any field in the active framework, add a
    # bounded alignment review before assuming entirely new source research is
    # required. This does not assert that the existing claims are sufficient.
    if (
        diagnostic.get("gap_classification") == "claims_exist_but_not_for_framework"
        and int(diagnostic.get("criterion_claims_available") or 0) > 0
    ):
        has_critical_gap = any(bool(gap.get("critical")) for gap in diagnostic.get("missing_questions") or [])
        items.append({
            "priority": "P1" if has_critical_gap else "P2",
            "action_type": "framework_alignment_review",
            "reason_code": "claims_available_but_none_match_active_framework_fields",
            "question_id": None,
            "question_label": None,
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

    return {
        "format": deepcopy(diagnostic.get("format") or {}),
        "analysis_status": diagnostic.get("analysis_status"),
        "risk_band": diagnostic.get("risk_band"),
        "band_suppressed_reason": diagnostic.get("band_suppressed_reason"),
        "evidence_completeness": diagnostic.get("evidence_completeness"),
        "gap_classification": diagnostic.get("gap_classification"),
        "criterion_claims_available": diagnostic.get("criterion_claims_available"),
        "remediation_item_count": len(items),
        "priority_counts": dict(sorted(priority_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "remediation_items": items,
        "evidence_hash": diagnostic.get("evidence_hash"),
    }


def summarize_evidence_remediation(rows: list[dict[str, Any]], *, candidate_count: int) -> dict[str, Any]:
    action_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    question_action_counts: dict[str, Counter[str]] = {}

    for row in rows:
        for item in row.get("remediation_items") or []:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "unknown")
            priority = str(item.get("priority") or "unknown")
            action_counts[action_type] += 1
            priority_counts[priority] += 1
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
        "question_action_counts": {
            question_id: dict(sorted(counts.items()))
            for question_id, counts in sorted(question_action_counts.items())
        },
    }
