from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.data_access import RegistryReader


_NATIVE_SUSTAINABILITY_FIELDS = {
    "disclosure": "sustainability.disclosure",
    "documentation": "sustainability.disclosure",
    "adoption": "sustainability.adoption",
    "transparency": "sustainability.transparency_readability",
    "self_documentation": "sustainability.self_documentation",
    "external_dependencies": "sustainability.external_dependencies",
    "impact_of_patents": "sustainability.ip_licensing",
    "technical_protection_mechanisms": "sustainability.tpm_encryption",
}
_STRONG_IDENTIFIER_FIELDS = {
    "puid": "puids",
    "loc": "loc_ids",
    "nara": "nara_ids",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _identifier_values(record: dict[str, Any], kind: str) -> list[str]:
    values: list[str] = []
    direct_field = _STRONG_IDENTIFIER_FIELDS.get(kind)
    if direct_field:
        for value in _as_list(record.get(direct_field)):
            _append_unique(values, value)

    identifiers = record.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in _as_list(identifiers.get(kind)):
            _append_unique(values, value)
    elif isinstance(identifiers, list):
        for item in identifiers:
            if not isinstance(item, dict) or str(item.get("kind") or item.get("type") or "").lower() != kind:
                continue
            for value in _as_list(item.get("value")):
                _append_unique(values, value)
    return values


def _latest_source_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for row in rows:
        source_id = str(row.get("source_id") or row.get("source_type") or "").strip()
        source_record_id = str(row.get("source_record_id") or "").strip()
        if not source_id or not source_record_id:
            continue
        key = (source_id, source_record_id)
        sort_key = str(row.get("run_id") or row.get("observed_at") or "")
        if key not in latest or sort_key >= latest[key][0]:
            latest[key] = (sort_key, row)
    return [item[1] for item in latest.values()]


def _direct_source_refs(format_doc: dict[str, Any]) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for ref in format_doc.get("source_records") or []:
        if not isinstance(ref, dict):
            continue
        source_id = str(ref.get("source_id") or ref.get("source_type") or "").strip()
        source_record_id = str(ref.get("source_record_id") or "").strip()
        if source_id and source_record_id:
            refs.add((source_id, source_record_id))
    return refs


def _format_identifier_sets(format_doc: dict[str, Any]) -> dict[str, set[str]]:
    return {
        kind: {value.lower() for value in _identifier_values(format_doc, kind)}
        for kind in _STRONG_IDENTIFIER_FIELDS
    }


def _shared_identifiers(format_ids: dict[str, set[str]], source_record: dict[str, Any]) -> list[dict[str, str]]:
    shared: list[dict[str, str]] = []
    for kind in _STRONG_IDENTIFIER_FIELDS:
        source_values = {value.lower(): value for value in _identifier_values(source_record, kind)}
        for normalized in sorted(format_ids.get(kind, set()).intersection(source_values)):
            shared.append({"kind": kind, "value": source_values[normalized]})
    return shared


def _source_url(source_record: dict[str, Any]) -> str | None:
    urls = source_record.get("urls") or {}
    if isinstance(urls, dict):
        for key in ("loc", "pronom", "nara", "source", "loc_source", "pronom_json"):
            value = urls.get(key)
            if value:
                return str(value)
    for key in ("source_url", "url", "uri"):
        value = source_record.get(key)
        if value:
            return str(value)
    return None


def _exact_authority_record_match(
    source_record: dict[str, Any],
    format_ids: dict[str, set[str]],
) -> dict[str, str] | None:
    """Return the authority identifier when this is the exact authority record.

    Shared identifiers can also occur on family/related records. Matching the
    source record's own authority ID is stronger: LOC fdd000248 is the exact LOC
    record for a canonical format carrying loc=fdd000248, whereas an LOC family
    record that merely mentions fmt/505 is related evidence rather than the exact
    version record.
    """
    source_id = str(source_record.get("source_id") or source_record.get("source_type") or "").lower()
    source_record_id = str(source_record.get("source_record_id") or "").strip()
    normalized = source_record_id.lower()
    if not normalized:
        return None
    if "loc" in source_id and normalized in format_ids.get("loc", set()):
        return {"kind": "loc", "value": source_record_id}
    if "pronom" in source_id and normalized in format_ids.get("puid", set()):
        return {"kind": "puid", "value": source_record_id}
    if "nara" in source_id and normalized in format_ids.get("nara", set()):
        return {"kind": "nara", "value": source_record_id}
    return None


def _link_basis(
    source_record: dict[str, Any],
    *,
    direct_refs: set[tuple[str, str]],
    format_ids: dict[str, set[str]],
) -> dict[str, Any] | None:
    source_id = str(source_record.get("source_id") or source_record.get("source_type") or "").strip()
    source_record_id = str(source_record.get("source_record_id") or "").strip()
    direct = (source_id, source_record_id) in direct_refs
    shared = _shared_identifiers(format_ids, source_record)
    exact_authority = _exact_authority_record_match(source_record, format_ids)
    if not direct and not shared and exact_authority is None:
        return None
    if direct:
        specificity = "direct_source_record"
    elif exact_authority is not None:
        specificity = "exact_authority_record"
    else:
        specificity = "shared_identifier_related_record"
    result: dict[str, Any] = {
        "specificity": specificity,
        "direct_source_record": direct,
        "shared_strong_identifiers": shared,
    }
    if exact_authority is not None:
        result["exact_authority_identifier"] = exact_authority
    return result


def _native_sustainability_items(source_record: dict[str, Any], link_basis: dict[str, Any]) -> list[dict[str, Any]]:
    native_fields = source_record.get("native_fields") or {}
    factors = native_fields.get("sustainability_factors") if isinstance(native_fields, dict) else None
    if not isinstance(factors, dict):
        return []

    items: list[dict[str, Any]] = []
    for native_key, evidence_field in _NATIVE_SUSTAINABILITY_FIELDS.items():
        source_value = factors.get(native_key)
        if source_value in (None, "", [], {}):
            continue
        item = {
            "evidence_section": "ai_source_evidence",
            "evidence_kind": (
                "source_native_documentation"
                if native_key == "documentation"
                else "source_native_sustainability_factor"
            ),
            "evidence_field": evidence_field,
            "native_field": f"native_fields.sustainability_factors.{native_key}",
            "source_id": source_record.get("source_id"),
            "source_type": source_record.get("source_type"),
            "source_record_id": source_record.get("source_record_id"),
            "source_name": source_record.get("name"),
            "source_value": deepcopy(source_value),
            "link_basis": deepcopy(link_basis),
        }
        url = _source_url(source_record)
        if url:
            item["source_url"] = url
        items.append(item)
    return items


def _source_native_risk_items(source_record: dict[str, Any], link_basis: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose source-native risk findings without treating them as governed mappings.

    These items are AI-only evidence. A new adapter/source may therefore provide a
    native risk assessment before a reviewed normalization rule exists. The AI may
    interpret it when enabled, but deterministic synthesis still requires policy
    mapping or an already normalized governed claim.
    """
    candidates: list[dict[str, Any]] = []
    for assessment in source_record.get("risk_assessments") or []:
        if not isinstance(assessment, dict):
            continue
        candidates.append(dict(assessment))
    hazard = source_record.get("hazard")
    if isinstance(hazard, dict):
        candidates.append(dict(hazard))

    items: list[dict[str, Any]] = []
    for assessment in candidates:
        if not any(
            assessment.get(key) is not None
            for key in ("native_label", "risk_level", "band", "classification", "native_score", "rating", "semantic_level")
        ):
            continue
        item: dict[str, Any] = {
            "evidence_section": "ai_source_evidence",
            "evidence_kind": "source_native_risk_assessment",
            "source_id": source_record.get("source_id") or assessment.get("source_id"),
            "source_type": source_record.get("source_type") or assessment.get("source_type"),
            "source_record_id": source_record.get("source_record_id") or assessment.get("source_record_id"),
            "source_name": source_record.get("name") or assessment.get("source_label"),
            "native_label": assessment.get("native_label") or assessment.get("risk_level") or assessment.get("band") or assessment.get("classification"),
            "native_score": assessment.get("native_score") if assessment.get("native_score") is not None else assessment.get("rating"),
            "native_scale": assessment.get("native_scale"),
            "semantic_level": assessment.get("semantic_level"),
            "scope_type": assessment.get("scope_type"),
            "scope_name": assessment.get("scope_name"),
            "source_value": deepcopy(assessment),
            "link_basis": deepcopy(link_basis),
        }
        url = _source_url(source_record)
        if url:
            item["source_url"] = url
        items.append({key: value for key, value in item.items() if value is not None})
    return items


def _generic_source_item(source_record: dict[str, Any], link_basis: dict[str, Any]) -> dict[str, Any] | None:
    description = source_record.get("description")
    if not description:
        raw = source_record.get("raw") or {}
        raw_record = raw.get("record") if isinstance(raw, dict) else None
        if isinstance(raw_record, dict):
            description = raw_record.get("formatDescription") or raw_record.get("formatNote")
    if not description:
        return None
    item: dict[str, Any] = {
        "evidence_section": "ai_source_evidence",
        "evidence_kind": "source_native_description",
        "source_id": source_record.get("source_id"),
        "source_type": source_record.get("source_type"),
        "source_record_id": source_record.get("source_record_id"),
        "source_name": source_record.get("name"),
        "source_value": deepcopy(description),
        "link_basis": deepcopy(link_basis),
    }
    url = _source_url(source_record)
    if url:
        item["source_url"] = url
    return item


def _specificity_rank(link_basis: dict[str, Any]) -> int:
    return {
        "direct_source_record": 0,
        "exact_authority_record": 1,
        "shared_identifier_related_record": 2,
    }.get(str(link_basis.get("specificity") or ""), 3)


def build_ai_source_evidence(
    reader: RegistryReader,
    format_doc: dict[str, Any],
    *,
    max_source_records: int = 80,
    max_items: int = 120,
) -> list[dict[str, Any]]:
    """Return bounded raw/source-native evidence for AI-only risk interpretation.

    This evidence is deliberately separate from criterion_claims. Deterministic
    derivation ignores ``ai_source_evidence``; the AI layer may inspect it only
    for questions that remain unresolved. A source record is eligible when it is
    directly attached to the canonical format or shares a strong identifier with
    it. Exact authority records are ranked ahead of broader related/family records.
    If the active registry reader does not expose source records, this optional
    layer fails closed to an empty list and the existing deterministic/AI-claim
    workflow continues.
    """
    max_source_records = max(1, int(max_source_records))
    max_items = max(1, int(max_items))
    direct_refs = _direct_source_refs(format_doc)
    format_ids = _format_identifier_sets(format_doc)

    query = getattr(reader, "query", None)
    if not callable(query):
        return []
    try:
        source_rows = query("source_records", {})
    except Exception:
        return []

    linked: list[tuple[int, str, str, dict[str, Any], dict[str, Any]]] = []
    for source_record in _latest_source_records(source_rows):
        link = _link_basis(source_record, direct_refs=direct_refs, format_ids=format_ids)
        if link is None:
            continue
        source_id = str(source_record.get("source_id") or source_record.get("source_type") or "")
        source_record_id = str(source_record.get("source_record_id") or "")
        linked.append((_specificity_rank(link), source_id, source_record_id, source_record, link))

    linked.sort(key=lambda item: (item[0], item[1], item[2]))
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, _, source_record, link in linked[:max_source_records]:
        candidates = _source_native_risk_items(source_record, link)
        candidates.extend(_native_sustainability_items(source_record, link))
        generic = _generic_source_item(source_record, link)
        if generic is not None:
            candidates.append(generic)
        for item in candidates:
            key = repr(item)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if len(items) >= max_items:
                return items
    return items
