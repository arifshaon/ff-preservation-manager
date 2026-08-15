from __future__ import annotations

from collections import defaultdict
from typing import Any

from registry_builder.models import CanonicalFormat

STRONG_IDENTIFIER_KINDS = {"puid", "loc", "nara"}


def _unique_owner_ids(owners: list[dict[str, Any]]) -> set[str]:
    return {str(owner.get("canonical_id") or "") for owner in owners if owner.get("canonical_id")}


def _claim_owner(fmt: CanonicalFormat, claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": fmt.canonical_id,
        "preferred_name": fmt.preferred_name,
        "kind": claim.get("kind"),
        "value": claim.get("value"),
        "source": claim.get("source"),
        "source_record_id": claim.get("source_record_id"),
        "verified": bool(claim.get("verified", False)),
        "confidence": claim.get("confidence"),
        "confidence_reason": claim.get("confidence_reason"),
    }


def build_collision_report(registry: list[CanonicalFormat], *, sample_limit: int = 50) -> dict[str, Any]:
    """Return auditable identifier collision and bridge diagnostics.

    This report is intentionally separate from preservation-risk analysis. It is
    a registry-quality gate: heuristic copied-ID bridges and identifier overlaps
    should be reviewed before downstream systems consume the registry as
    evidence.
    """
    identifier_seen: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    verified_strong_seen: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    heuristic_identifier_bridges: list[dict[str, Any]] = []

    for fmt in registry:
        for claim in fmt.identifier_claims:
            kind = str(claim.get("kind") or "").strip().lower()
            value = str(claim.get("value") or "").strip()
            if not kind or not value:
                continue
            owner = _claim_owner(fmt, claim)
            identifier_seen[(kind, value)].append(owner)
            if claim.get("verified") and kind in STRONG_IDENTIFIER_KINDS:
                verified_strong_seen[(kind, value)].append(owner)
            if claim.get("confidence") == "heuristic":
                heuristic_identifier_bridges.append(owner)

    weak_identifier_overlaps: list[dict[str, Any]] = []
    for (kind, value), owners in sorted(identifier_seen.items()):
        canonical_ids = sorted(_unique_owner_ids(owners))
        if kind in STRONG_IDENTIFIER_KINDS or len(canonical_ids) <= 1:
            continue
        weak_identifier_overlaps.append({
            "kind": kind,
            "value": value,
            "canonical_ids": canonical_ids,
            "owners": owners[:sample_limit],
        })

    verified_strong_identifier_conflicts: list[dict[str, Any]] = []
    for (kind, value), owners in sorted(verified_strong_seen.items()):
        canonical_ids = sorted(_unique_owner_ids(owners))
        if len(canonical_ids) <= 1:
            continue
        verified_strong_identifier_conflicts.append({
            "kind": kind,
            "value": value,
            "canonical_ids": canonical_ids,
            "owners": owners[:sample_limit],
        })

    summary = {
        "heuristic_identifier_bridges": len(heuristic_identifier_bridges),
        "weak_identifier_overlaps": len(weak_identifier_overlaps),
        "verified_strong_identifier_conflicts": len(verified_strong_identifier_conflicts),
    }
    status = "error" if verified_strong_identifier_conflicts else "review" if any(summary.values()) else "ok"
    return {
        "status": status,
        "summary": summary,
        "heuristic_identifier_bridges": heuristic_identifier_bridges[:sample_limit],
        "weak_identifier_overlaps": weak_identifier_overlaps[:sample_limit],
        "verified_strong_identifier_conflicts": verified_strong_identifier_conflicts[:sample_limit],
    }


def collision_report_counts(report: dict[str, Any]) -> dict[str, int]:
    return {key: int(value) for key, value in (report.get("summary") or {}).items()}
