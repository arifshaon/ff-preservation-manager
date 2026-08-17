from __future__ import annotations

import re
from typing import Any

from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.request_api import search_family_docs


_PUID_OBSERVATION = re.compile(
    r"(?:pronom\s*)?(?:x?-?fmt)\s*[:/\- ]\s*\d+$",
    re.IGNORECASE,
)


def _as_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _canonical_id(row: dict[str, Any]) -> str:
    return str(row.get("canonical_id") or row.get("format_id") or row.get("id") or "").strip()


def _label(row: dict[str, Any]) -> str:
    return str(
        row.get("preferred_name")
        or row.get("format_name")
        or row.get("name")
        or row.get("label")
        or _canonical_id(row)
    ).strip()


def _puid_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("puids", "puid"):
        for value in _as_values(row.get(field)):
            normalized = value.lower()
            if re.fullmatch(r"(?:x-fmt|fmt)/\d+", normalized) and normalized not in values:
                values.append(normalized)

    identifiers = row.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in _as_values(identifiers.get("puid")):
            normalized = value.lower()
            if re.fullmatch(r"(?:x-fmt|fmt)/\d+", normalized) and normalized not in values:
                values.append(normalized)
    return values


def _looks_like_explicit_puid(value: str) -> bool:
    compact = str(value or "").strip().strip("[](){}<>,;\"'").strip()
    return bool(_PUID_OBSERVATION.fullmatch(compact))


def _candidate_ids_from_identification(identification: dict[str, Any]) -> set[str]:
    ai = identification.get("ai") or {}
    values = (
        identification.get("ambiguity_candidate_canonical_ids")
        or ai.get("candidate_canonical_ids")
        or []
    )
    return {str(value).strip() for value in values if str(value).strip()}


def _candidate_summaries(identification: dict[str, Any]) -> list[dict[str, Any]]:
    matched = identification.get("matched_candidates") or []
    if matched:
        return [item for item in matched if isinstance(item, dict)]

    wanted = _candidate_ids_from_identification(identification)
    ai = identification.get("ai") or {}
    rows = [item for item in ai.get("candidates") or [] if isinstance(item, dict)]
    if wanted:
        rows = [item for item in rows if str(item.get("canonical_id") or "") in wanted]
    return rows


def _resolve_summary_rows(reader: RegistryReader, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolver = FormatResolver(reader)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for summary in summaries:
        canonical_id = str(summary.get("canonical_id") or "").strip()
        if not canonical_id or canonical_id in seen:
            continue
        resolution = resolver.resolve(canonical_id)
        if resolution.resolved and resolution.format_doc:
            rows.append(resolution.format_doc)
            seen.add(canonical_id)
    return rows


def _preference(row: dict[str, Any]) -> tuple[int, int, str]:
    canonical_id = _canonical_id(row).lower()
    puids = _puid_values(row)
    # Prefer the canonical PRONOM/PUID-centric record when duplicate source-centric
    # canonical rows share the same PUID. The risk reader still follows strong
    # aliases, so evidence from linked source records remains available.
    return (
        2 if canonical_id.startswith("puid-") else 0,
        1 if len(puids) == 1 else 0,
        canonical_id,
    )


def _puid_sort_key(puid: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"(x-fmt|fmt)/(\d+)", str(puid).lower())
    if not match:
        return (2, 0, str(puid))
    return (0 if match.group(1) == "fmt" else 1, int(match.group(2)), str(puid))


def human_puid_candidates(
    reader: RegistryReader,
    request: dict[str, Any],
    identification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return one preferred canonical record per PUID for a human-format query.

    Human questions are allowed to fan out across several plausible PUIDs. This
    is deliberately different from the structured machine path, where callers are
    expected to supply a precise identifier and ambiguity remains an error.

    Exact PUID observations are excluded here so they continue down the normal
    single-format deterministic path. For human names such as ``PDF``, an exact
    name match may be expanded through the existing family/name discovery helper.
    For AI ambiguity, only the locally supplied candidates accepted as plausible
    by the identification layer are considered.
    """
    if not identification:
        return []
    action = str(request.get("action") or "").strip()
    if action not in {"assess_format", "assess_format_questions"}:
        return []

    format_value = str(request.get("format") or "").strip()
    if not format_value or _looks_like_explicit_puid(format_value):
        return []

    pool: list[dict[str, Any]] = []
    pool.extend(_resolve_summary_rows(reader, _candidate_summaries(identification)))

    resolved_id = str(identification.get("resolved_canonical_id") or "").strip()
    if resolved_id:
        resolution = FormatResolver(reader).resolve(resolved_id)
        if resolution.resolved and resolution.format_doc:
            pool.append(resolution.format_doc)

    match_type = str(identification.get("match_type") or "")
    if identification.get("status") == "resolved" and match_type in {"name", "alias"}:
        seed = str(identification.get("resolved_label") or format_value).strip()
        if seed:
            pool.extend(search_family_docs(reader, seed, limit=int(request.get("limit") or 100)))

    # Do not invent a family expansion from a failed descriptive lookup. If the
    # identification stage has no defensible local rows, the caller should retain
    # its normal not-found/ambiguity behavior.
    if not pool:
        return []

    selected_puids: set[str] = set()
    for row in pool:
        selected_puids.update(_puid_values(row))
    if not selected_puids:
        return []

    # Build a registry-wide PUID index only for the selected identifiers so
    # source-centric duplicates do not consume separate assessment slots.
    by_puid: dict[str, list[dict[str, Any]]] = {puid: [] for puid in selected_puids}
    for row in reader.list_canonical_formats():
        for puid in _puid_values(row):
            if puid in by_puid:
                by_puid[puid].append(row)

    limit = max(1, int(request.get("limit") or 100))
    results: list[dict[str, Any]] = []
    for puid in sorted(selected_puids, key=_puid_sort_key)[:limit]:
        rows = by_puid.get(puid) or []
        if not rows:
            continue
        preferred = sorted(rows, key=_preference, reverse=True)[0]
        results.append(
            {
                "puid": puid,
                "canonical_id": _canonical_id(preferred),
                "label": _label(preferred),
                "version": preferred.get("version"),
                "format_doc": preferred,
            }
        )
    return results
