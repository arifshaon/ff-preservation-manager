from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

GLOBAL_EVIDENCE_KEYS = (
    "global_evidence",
    "risk_evidence",
    "evidence_claims",
    "source_evidence_claims",
)
INSTITUTION_EVIDENCE_KEYS = (
    "institution_evidence_claims",
    "institution_evidence",
)
MIGRATION_PATHWAY_KEYS = (
    "migration_pathway_evidence",
    "migration_pathways",
)
LOCAL_MIGRATION_READINESS_KEYS = (
    "local_migration_readiness",
    "institution_migration_readiness",
    "institution_migration_readiness_claims",
)
VOLATILE_HASH_KEYS = {
    "evidence_hash",
    "computed_at",
    "created_at",
    "updated_at",
    "last_seen_at",
    "modified_at",
}
EXCLUDED_REVIEW_STATUSES = {"draft", "rejected", "withdrawn", "superseded"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _identifier_bucket(format_record: dict[str, Any], kind: str) -> list[Any]:
    identifiers = format_record.get("identifiers") or {}
    if isinstance(identifiers, dict):
        return deepcopy(_as_list(identifiers.get(kind)))
    return []


def _collect(record: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in keys:
        for item in _as_list(record.get(key)):
            if isinstance(item, dict):
                items.append(deepcopy(item))
    return items


def _review_status(item: dict[str, Any]) -> str | None:
    status = item.get("review_status")
    return str(status).lower() if status is not None else None


def _is_usable_evidence(item: dict[str, Any], *, include_unapproved: bool) -> bool:
    if include_unapproved:
        return True
    return _review_status(item) not in EXCLUDED_REVIEW_STATUSES


def _usable_items(items: list[dict[str, Any]], *, include_unapproved: bool) -> list[dict[str, Any]]:
    return [item for item in items if _is_usable_evidence(item, include_unapproved=include_unapproved)]


def _is_institution_scoped(item: dict[str, Any]) -> bool:
    if item.get("institution_id"):
        return True
    return str(item.get("source_independence") or "").lower() == "institution_scoped"


def _split_criterion_claims(
    items: list[dict[str, Any]],
    *,
    institution_id: str | None,
    include_unapproved: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    global_claims: list[dict[str, Any]] = []
    institution_claims: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        claim = deepcopy(item)
        if not _is_usable_evidence(claim, include_unapproved=include_unapproved):
            continue
        if not _is_institution_scoped(claim):
            global_claims.append(claim)
            continue
        if institution_id and str(claim.get("institution_id") or "") == institution_id:
            institution_claims.append(claim)
    return global_claims, institution_claims


def _institution_items(
    items: list[dict[str, Any]],
    *,
    institution_id: str,
    include_unapproved: bool,
) -> list[dict[str, Any]]:
    scoped: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("institution_id") or "") != institution_id:
            continue
        if not _is_usable_evidence(item, include_unapproved=include_unapproved):
            continue
        scoped.append(item)
    return scoped


def format_identity(format_record: dict[str, Any]) -> dict[str, Any]:
    """Extract stable identity fields from a registry format record."""
    return {
        "format_id": (
            format_record.get("canonical_id")
            or format_record.get("format_id")
            or format_record.get("id")
        ),
        "label": (
            format_record.get("format_name")
            or format_record.get("preferred_name")
            or format_record.get("name")
            or format_record.get("label")
        ),
        "identifiers": deepcopy(format_record.get("identifiers") or []),
        "puids": deepcopy(format_record.get("puids") or _identifier_bucket(format_record, "puid")),
        "loc_ids": deepcopy(format_record.get("loc_ids") or _identifier_bucket(format_record, "loc")),
        "nara_ids": deepcopy(format_record.get("nara_ids") or _identifier_bucket(format_record, "nara")),
        "extensions": deepcopy(format_record.get("extensions") or _identifier_bucket(format_record, "extension")),
        "mime_types": deepcopy(format_record.get("mime_types") or _identifier_bucket(format_record, "mime")),
    }


def build_evidence_pack(
    format_record: dict[str, Any],
    *,
    institution_id: str | None = None,
    criterion_claims: list[dict[str, Any]] | None = None,
    local_migration_readiness: list[dict[str, Any]] | None = None,
    include_unapproved: bool = False,
) -> dict[str, Any]:
    """Build an evidence pack for global or institution-scoped analysis.

    The registry remains the evidence source. Global packs contain only global
    evidence and authority-asserted migration pathways. Institution packs add
    institution-scoped evidence and local migration readiness for the requested
    institution only.
    """
    global_criterion_claims, institution_criterion_claims = _split_criterion_claims(
        criterion_claims or [],
        institution_id=institution_id,
        include_unapproved=include_unapproved,
    )
    pack: dict[str, Any] = {
        "scope": "institution" if institution_id else "global",
        "format": format_identity(format_record),
        "global_evidence": _usable_items(
            _collect(format_record, GLOBAL_EVIDENCE_KEYS) + global_criterion_claims,
            include_unapproved=include_unapproved,
        ),
        "migration_pathway_evidence": _usable_items(
            _collect(format_record, MIGRATION_PATHWAY_KEYS),
            include_unapproved=include_unapproved,
        ),
    }

    if institution_id:
        readiness_from_record = _collect(format_record, LOCAL_MIGRATION_READINESS_KEYS)
        readiness_from_argument = [deepcopy(item) for item in (local_migration_readiness or [])]
        pack.update({
            "institution_id": institution_id,
            "institution_evidence": _institution_items(
                _collect(format_record, INSTITUTION_EVIDENCE_KEYS),
                institution_id=institution_id,
                include_unapproved=include_unapproved,
            ) + institution_criterion_claims,
            "local_migration_readiness": _institution_items(
                readiness_from_record + readiness_from_argument,
                institution_id=institution_id,
                include_unapproved=include_unapproved,
            ),
        })

    pack["evidence_hash"] = evidence_hash(pack)
    return pack


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonicalize(val)
            for key, val in sorted(value.items())
            if key not in VOLATILE_HASH_KEYS
        }
    if isinstance(value, list):
        canonical_items = [_canonicalize(item) for item in value]
        return sorted(canonical_items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, tuple):
        return _canonicalize(list(value))
    return value


def canonical_json(value: Any) -> str:
    """Return stable JSON for hashing evidence semantics, not insertion order."""
    return json.dumps(_canonicalize(value), sort_keys=True, separators=(",", ":"), default=str)


def evidence_hash(evidence_pack: dict[str, Any]) -> str:
    """Return a stable SHA-256 hash for an evidence pack."""
    return hashlib.sha256(canonical_json(evidence_pack).encode("utf-8")).hexdigest()
