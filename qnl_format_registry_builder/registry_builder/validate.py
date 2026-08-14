from __future__ import annotations

from collections import defaultdict
from registry_builder.models import CanonicalFormat


def validate_registry(registry: list[CanonicalFormat]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ids = set()
    identifier_seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fmt in registry:
        if fmt.canonical_id in ids:
            errors.append(f"duplicate canonical_id: {fmt.canonical_id}")
        ids.add(fmt.canonical_id)
        if not fmt.preferred_name:
            errors.append(f"{fmt.canonical_id}: missing preferred_name")
        for kind, values in fmt.identifiers.items():
            for value in values:
                identifier_seen[(kind, value)].append(fmt.canonical_id)
    for (kind, value), owners in identifier_seen.items():
        if len(set(owners)) > 1 and kind in {"puid", "loc", "nara", "mime"}:
            warnings.append(f"identifier {kind}:{value} appears in multiple canonical records: {sorted(set(owners))}")
    return errors, warnings
