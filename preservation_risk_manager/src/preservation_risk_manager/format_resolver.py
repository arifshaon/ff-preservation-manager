from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from preservation_risk_manager.data_access import RegistryReader


@dataclass(frozen=True)
class FormatResolution:
    query: str
    status: str
    match_type: str | None = None
    format_doc: dict[str, Any] | None = None
    matches: tuple[dict[str, Any], ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == "resolved"

    @property
    def ambiguous(self) -> bool:
        return self.status == "ambiguous"

    @property
    def not_found(self) -> bool:
        return self.status == "not_found"


def _normalize(value: Any) -> str:
    return str(value).strip().lower()


def _normalize_extension(value: Any) -> str:
    return _normalize(value).lstrip(".")


def _as_iter(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return value
    return (value,)


def _field_values(format_doc: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for field in fields:
        for item in _as_iter(format_doc.get(field)):
            values.add(_normalize(item))
    return {value for value in values if value}


def _extension_values(format_doc: dict[str, Any]) -> set[str]:
    return {_normalize_extension(value) for value in _field_values(format_doc, ("extensions", "extension", "file_extensions"))}


def _identifier_values(format_doc: dict[str, Any]) -> set[str]:
    values = set()
    for field in ("puids", "loc_ids", "nara_ids", "wikidata_ids"):
        values.update(_field_values(format_doc, (field,)))
    for identifier in _as_iter(format_doc.get("identifiers")):
        if not isinstance(identifier, dict):
            values.add(_normalize(identifier))
            continue
        for key in ("value", "id", "identifier", "identifier_value"):
            if identifier.get(key):
                values.add(_normalize(identifier[key]))
    return {value for value in values if value}


def _candidate_match(format_doc: dict[str, Any], query: str) -> tuple[int, str] | None:
    normalized = _normalize(query)
    normalized_ext = _normalize_extension(query)

    if normalized in _field_values(format_doc, ("canonical_id", "format_id", "id")):
        return (100, "canonical_id")
    if normalized in _identifier_values(format_doc):
        return (90, "authority_identifier")
    if normalized in _field_values(format_doc, ("mime_types", "mime_type", "mimes")):
        return (80, "mime_type")
    if normalized_ext and normalized_ext in _extension_values(format_doc):
        return (70, "extension")
    if normalized in _field_values(format_doc, ("name", "label", "short_name", "display_name")):
        return (60, "name")
    if normalized in _field_values(format_doc, ("aliases", "alternative_names")):
        return (50, "alias")
    return None


def resolve_format(query: str, format_docs: Iterable[dict[str, Any]]) -> FormatResolution:
    """Resolve a user-supplied format token against canonical format documents.

    Resolution is strict by design: exact IDs and identifiers have highest
    precedence; extensions and names must identify a single top-priority match.
    Ambiguity is reported instead of guessed.
    """
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for format_doc in format_docs:
        match = _candidate_match(format_doc, query)
        if match:
            priority, match_type = match
            candidates.append((priority, match_type, format_doc))

    if not candidates:
        return FormatResolution(query=query, status="not_found")

    highest_priority = max(priority for priority, _, _ in candidates)
    top = [(match_type, format_doc) for priority, match_type, format_doc in candidates if priority == highest_priority]
    match_type = top[0][0]
    matches = tuple(format_doc for _, format_doc in top)
    if len(matches) > 1:
        return FormatResolution(query=query, status="ambiguous", match_type=match_type, matches=matches)
    return FormatResolution(
        query=query,
        status="resolved",
        match_type=match_type,
        format_doc=matches[0],
        matches=matches,
    )


class FormatResolver:
    """Resolve format tokens using canonical formats read from a RegistryReader."""

    def __init__(self, reader: RegistryReader) -> None:
        self.reader = reader

    def resolve(self, query: str) -> FormatResolution:
        return resolve_format(query, self.reader.list_canonical_formats())
