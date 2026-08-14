from __future__ import annotations

from collections import defaultdict
from registry_builder.models import CanonicalFormat


_STRONG_IDENTIFIER_KINDS = {"puid", "loc", "nara"}


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

    for (kind, value), owners in verified_identifier_seen.items():
        if len(set(owners)) > 1 and kind in _STRONG_IDENTIFIER_KINDS:
            errors.append(f"verified identifier {kind}:{value} appears in multiple canonical records: {sorted(set(owners))}")
    for (kind, value), owners in identifier_seen.items():
        if len(set(owners)) > 1 and kind not in _STRONG_IDENTIFIER_KINDS:
            warnings.append(f"weak identifier {kind}:{value} appears in multiple canonical records: {sorted(set(owners))}")
    for (institution_id, institution_format_id), owners in institution_policy_id_seen.items():
        if len(owners) > 1:
            warnings.append(
                f"institutional policy identifier {institution_id}:{institution_format_id} appears in multiple source rows/canonical records: {owners}"
            )
    return errors, warnings
