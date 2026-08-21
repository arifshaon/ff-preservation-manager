from __future__ import annotations

from copy import deepcopy
from typing import Any

from registry_builder.utils import normalize_extension, normalize_identifier, normalize_mime

DEFAULT_IDENTIFIER_KINDS: dict[str, dict[str, Any]] = {
    "extension": {"strength": "weak", "verified_from": []},
    "mime": {"strength": "weak", "verified_from": []},
    "puid": {"strength": "strong", "verified_from": ["pronom_registry", "pronom_droid_xml"]},
    "loc": {"strength": "strong", "verified_from": ["loc_fdd_xml"]},
    "nara": {
        "strength": "strong",
        "verified_from": ["nara_digital_preservation_framework", "nara_lod", "nara_json", "nara", "nara_preservation_csv"],
    },
    "wikidata": {"strength": "weak", "verified_from": ["wikidata"]},
}


def load_identifier_rules(configured: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Merge configured identifier rules over built-in defaults.

    Configuration shape:

    {
      "dpc": {"strength": "strong", "verified_from": ["dpc_bit_list"]}
    }

    Built-in rules remain available unless explicitly overwritten. Non-dict
    entries such as `notes` are ignored so config files can remain readable.
    """
    rules = deepcopy(DEFAULT_IDENTIFIER_KINDS)
    for kind, rule in (configured or {}).items():
        normalized_kind = str(kind).strip().lower()
        if normalized_kind in {"notes", "_notes", "comment", "_comment"} or not isinstance(rule, dict):
            continue
        merged = deepcopy(rules.get(normalized_kind, {}))
        merged.update(dict(rule or {}))
        merged.setdefault("strength", "weak")
        merged.setdefault("verified_from", [])
        rules[normalized_kind] = merged
    return rules


def normalize_identifier_value(kind: str, value: str) -> str:
    kind = kind.strip().lower()
    if kind == "extension":
        return normalize_extension(value)
    if kind == "mime":
        return normalize_mime(value)
    if kind == "loc":
        return normalize_identifier(value).lower()
    if kind == "wikidata":
        return normalize_identifier(value).upper()
    return normalize_identifier(value)


def is_verified_identifier(kind: str, source_type: str, rules: dict[str, dict[str, Any]]) -> bool:
    rule = rules.get(kind.strip().lower(), {})
    return source_type in set(rule.get("verified_from") or [])


def strong_identifier_order(rules: dict[str, dict[str, Any]]) -> list[str]:
    return [kind for kind, rule in rules.items() if str(rule.get("strength", "")).lower() == "strong"]


def strong_identifier_kinds(rules: dict[str, dict[str, Any]]) -> set[str]:
    return set(strong_identifier_order(rules))
