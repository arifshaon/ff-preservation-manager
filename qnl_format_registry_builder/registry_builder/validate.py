from __future__ import annotations

from collections import Counter, defaultdict
from registry_builder.collision_report import build_collision_report
from registry_builder.models import CanonicalFormat


_STRONG_IDENTIFIER_KINDS = {"puid", "loc", "nara"}


def _warning_type(warning: str) -> str:
    if warning.startswith("weak identifier "):
        return "weak_identifier_overlap"
    if warning.startswith("heuristic identifier bridge "):
        return "heuristic_identifier_bridge"
    if warning.startswith("institutional policy identifier "):
        return "institution_policy_duplicate"
    return "other"


def summarize_validation_warnings(warnings: list[str], sample_limit: int = 5) -> dict[str, dict]:
    """Group verbose validation warnings into reportable classes.

    Full warnings remain available in run_report.json, but large authority-source
    runs can produce hundreds of expected weak-identifier overlaps. The summary
    keeps actionable warning classes visible.
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for warning in warnings:
        grouped[_warning_type(warning)].append(warning)
    return {
        warning_type: {
            "count": len(items),
            "samples": items[:sample_limit],
        }
        for warning_type, items in sorted(grouped.items())
    }


def validation_warning_counts(warnings: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(_warning_type(warning) for warning in warnings).items()))


def validate_registry(registry: list[CanonicalFormat]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ids = set()
    identifier_seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    verified_identifier_seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    institution_policy_id_seen: dict[tuple[str, str], list[str]] = defaultdict(list)

    for fmt in registry:
        if fmt.canonical_id in ids:
            errors.append(f"duplicate canonical_id: {fmt.canonical_id}")
        ids.add(fmt.canonical_id)
        if not fmt.preferred_name:
            errors.append(f"{fmt.canonical_id}: missing preferred_name")
        for kind, values in fmt.identifiers.items():
            for value in values:
                identifier_seen[(kind, value)].append(fmt.canonical_id)
        for claim in fmt.identifier_claims:
            if claim.get("verified"):
                verified_identifier_seen[(claim.get("kind"), claim.get("value"))].append(fmt.canonical_id)
        for policy in fmt.institution_policy_overlays:
            institution_id = (policy.get("institution_id") or "unknown").strip()
            institution_format_id = (policy.get("institution_format_id") or "").strip()
            if institution_format_id:
                institution_policy_id_seen[(institution_id, institution_format_id)].append(
                    f"{fmt.canonical_id}@row:{policy.get('source_row', 'unknown')}"
                )

    # Strong identifiers in CanonicalFormat.identifiers are exact canonical
    # identity assertions. Cross-authority copied IDs are retained on
    # source_records as cross-reference metadata and must never make the same
    # PUID/LOC/NARA identifier appear on competing canonical records.
    for (kind, value), owners in identifier_seen.items():
        unique_owners = sorted(set(owners))
        if len(unique_owners) <= 1:
            continue
        if kind in _STRONG_IDENTIFIER_KINDS:
            errors.append(
                f"strong identifier {kind}:{value} appears in multiple canonical records: {unique_owners}"
            )
        else:
            warnings.append(
                f"weak identifier {kind}:{value} appears in multiple canonical records: {unique_owners}"
            )

    # Keep the verified-claim check as an additional integrity guard in case a
    # future code path accidentally omits a verified identifier from the compact
    # identifiers dictionary while retaining the provenance claim.
    for (kind, value), owners in verified_identifier_seen.items():
        if len(set(owners)) > 1 and kind in _STRONG_IDENTIFIER_KINDS:
            message = f"verified identifier {kind}:{value} appears in multiple canonical records: {sorted(set(owners))}"
            if message not in errors:
                errors.append(message)

    for bridge in build_collision_report(registry).get("heuristic_identifier_bridges", []):
        warnings.append(
            "heuristic identifier bridge "
            f"{bridge.get('kind')}:{bridge.get('value')} in {bridge.get('canonical_id')} "
            f"from {bridge.get('source')}: {bridge.get('confidence_reason') or 'review recommended'}"
        )
    for (institution_id, institution_format_id), owners in institution_policy_id_seen.items():
        if len(owners) > 1:
            warnings.append(
                f"institutional policy identifier {institution_id}:{institution_format_id} appears in multiple source rows/canonical records: {owners}"
            )
    return errors, warnings
