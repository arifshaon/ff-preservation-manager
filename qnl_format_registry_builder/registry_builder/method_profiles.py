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

    The assignment result is stored as a generated current view on each
    CanonicalFormat. It is not intended to replace QNL policy review. The goal
    is to provide scalable action-plan templates such as XML-based structured
    text, raster image, office document, audiovisual, archive/container, etc.,
    plus narrow modifiers like chemistry/scientific data for CML.
    """
    for fmt in registry:
        assigned = _matching_profile_ids(fmt, config.get("assignment_rules", []))
        fmt.preservation_method = build_preservation_method(assigned, config)
    return list(registry)


def build_preservation_method(profile_ids: list[str], config: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    ordered_ids: list[str] = []
    for profile_id in profile_ids:
        _append_with_inheritance(profile_id, profiles, ordered_ids)

    method: dict[str, Any] = {
        "profile_version": config.get("version", "unversioned"),
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
    matched: list[str] = []
    for rule in rules:
        if _matches(fmt, rule.get("match", {})):
            profile_id = rule.get("profile")
            if profile_id and profile_id not in matched:
                matched.append(profile_id)
    return matched


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


def _extend_unique(target: list[Any], values: list[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)
