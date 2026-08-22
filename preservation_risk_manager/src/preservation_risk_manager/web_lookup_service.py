from __future__ import annotations

from typing import Any

from preservation_risk_manager.request_api import search_format_docs
from preservation_risk_manager.web_service import WebRuntimeConfig, _reader


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _identifier_values(format_doc: dict[str, Any], kind: str, *direct_fields: str) -> list[str]:
    values: list[str] = []
    for field in direct_fields:
        for value in _as_list(format_doc.get(field)):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in _as_list(identifiers.get(kind)):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


def _label(format_doc: dict[str, Any]) -> str | None:
    value = (
        format_doc.get("preferred_name")
        or format_doc.get("format_name")
        or format_doc.get("name")
        or format_doc.get("label")
        or format_doc.get("display_name")
    )
    return str(value) if value is not None else None


def _canonical_id(format_doc: dict[str, Any]) -> str | None:
    value = format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id")
    return str(value) if value is not None else None


def _lookup_row(format_doc: dict[str, Any]) -> dict[str, Any]:
    puids = _identifier_values(format_doc, "puid", "puids")
    return {
        "puid": puids[0] if puids else None,
        "puids": puids,
        "canonical_id": _canonical_id(format_doc),
        "label": _label(format_doc),
        "version": str(format_doc.get("version")) if format_doc.get("version") is not None else None,
        "extensions": _identifier_values(
            format_doc,
            "extension",
            "extensions",
            "file_extensions",
            "extension",
        ),
        "mime_types": _identifier_values(format_doc, "mime", "mime_types", "mime_type"),
        "loc_ids": _identifier_values(format_doc, "loc", "loc_ids"),
        "nara_ids": _identifier_values(format_doc, "nara", "nara_ids"),
    }


def lookup_puids(reader, query: str, *, limit: int = 10) -> dict[str, Any]:
    """Find PRONOM-PUID-backed canonical formats by name, PUID, MIME, extension or other indexed text.

    The existing general format-discovery ranking is reused so exact values rank
    before substring matches. Results without a PUID are omitted because this
    endpoint is specifically the curator's PUID discovery workflow.
    """
    text = str(query or "").strip()
    if not text:
        raise ValueError("A format name, PUID, MIME type, extension, or identifier is required.")
    bounded_limit = max(1, int(limit))

    rows = search_format_docs(reader, text)
    puid_rows = [_lookup_row(row) for row in rows]
    puid_rows = [row for row in puid_rows if row.get("puid")]
    returned = puid_rows[:bounded_limit]
    return {
        "query": text,
        "match_count": len(puid_rows),
        "returned_count": len(returned),
        "limit": bounded_limit,
        "limit_applied": len(puid_rows) > bounded_limit,
        "matches": returned,
    }


def lookup_web_puids(config: WebRuntimeConfig, query: str, *, limit: int = 10) -> dict[str, Any]:
    return lookup_puids(_reader(config), query, limit=limit)
