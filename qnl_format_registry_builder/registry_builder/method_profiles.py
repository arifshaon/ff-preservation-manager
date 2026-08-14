from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from registry_builder.models import CanonicalFormat


def load_method_profile_config(path: str | Path) -> dict[str, Any]:
    """Load preservation method profile configuration.

    Method profiles are reusable action-plan templates. They are assigned by
    family/domain rules and optional overrides rather than authored separately
    for every file format.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assign_method_profiles(registry: Iterable[CanonicalFormat], config: dict[str, Any]) -> list[CanonicalFormat]:
    """Assign reusable preservation method profiles to canonical formats.

    Primary rules should be precise, usually based on identifiers such as
    extensions or verified source evidence. Fallback rules are broader category
    catches and are applied only when no primary rule matched. This prevents
    broad institutional categories such as "Textual and Word Processing" from
    adding office-document guidance to formats already identified as FASTA, CIF,
    XSD, or another more precise non-office format.
    """
    for fmt in registry:
        assigned = _matching_profile_ids(fmt, config.get("assignment_rules", []))
        fmt.preservation_method = build_preservation_method(assigned, config)
    return list(registry)


def build_preservation_method(profile_ids: list[str], config: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    direct_ids = _dedupe(profile_ids)
    ordered_ids: list[str] = []
    for profile_id in direct_ids:
        _append_with_inheritance(profile_id, profiles, ordered_ids)

    method: dict[str, Any] = {
        "profile_version": config.get("version", "unversioned"),
        "direct_profile_ids": direct_ids,
        "assigned_profile_ids": ordered_ids,
        "steps": [],
        "validation": [],
        "metadata_extraction": [],
        "derivative_guidance": [],
        "monitoring": [],
        "overrides": [],
        "notes": [],
    }
    for profile_id in ordered_ids:
        profile = profiles.get(profile_id, {})
        _extend_unique(method["steps"], profile.get("steps", []))
        _extend_unique(method["validation"], profile.get("validation", []))
        _extend_unique(method["metadata_extraction"], profile.get("metadata_extraction", []))
        _extend_unique(method["derivative_guidance"], profile.get("derivative_guidance", []))
        _extend_unique(method["monitoring"], profile.get("monitoring", []))
        _extend_unique(method["overrides"], profile.get("overrides", []))
        if profile.get("note"):
            _extend_unique(method["notes"], [profile["note"]])
    return method


def _append_with_inheritance(profile_id: str, profiles: dict[str, Any], ordered_ids: list[str]) -> None:
    if profile_id in ordered_ids:
        return
    profile = profiles.get(profile_id)
    if not profile:
        return
    for parent_id in profile.get("inherits", []):
        _append_with_inheritance(parent_id, profiles, ordered_ids)
    if profile_id not in ordered_ids:
        ordered_ids.append(profile_id)


def _matching_profile_ids(fmt: CanonicalFormat, rules: list[dict[str, Any]]) -> list[str]:
    """Return direct profile ids for a format.

    Rules marked `fallback_only: true` are evaluated only if no primary rules
    matched. This makes category rules a safety net rather than an additive
    broad classifier.
    """
    primary = [
        rule.get("profile")
        for rule in rules
        if not rule.get("fallback_only") and _matches(fmt, rule.get("match", {}))
    ]
    primary = _dedupe([profile_id for profile_id in primary if profile_id])
    if primary:
        return primary

    fallback = [
        rule.get("profile")
        for rule in rules
        if rule.get("fallback_only") and _matches(fmt, rule.get("match", {}))
    ]
    return _dedupe([profile_id for profile_id in fallback if profile_id])


def _matches(fmt: CanonicalFormat, matcher: dict[str, Any]) -> bool:
    if not matcher:
        return False
    text = " ".join(
        value.lower()
        for value in [fmt.preferred_name or "", fmt.category or "", fmt.description or ""]
        if value
    )
    identifiers = fmt.identifiers or {}

    if matcher.get("name_contains"):
        if not any(term.lower() in text for term in matcher["name_contains"]):
            return False
    if matcher.get("category_contains"):
        if not any(term.lower() in (fmt.category or "").lower() for term in matcher["category_contains"]):
            return False
    for identifier_type, values in matcher.get("identifiers", {}).items():
        expected = {str(v).lower().lstrip(".") for v in values}
        actual = {str(v).lower().lstrip(".") for v in identifiers.get(identifier_type, [])}
        if expected and actual.isdisjoint(expected):
            return False
    return True


def _dedupe(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _extend_unique(target: list[Any], values: list[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)
