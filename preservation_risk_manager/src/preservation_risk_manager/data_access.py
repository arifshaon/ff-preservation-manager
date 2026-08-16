from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol

from preservation_risk_manager.errors import PreservationRiskManagerError


class RegistryAccessError(PreservationRiskManagerError):
    """Raised when registry evidence cannot be accessed through the reader."""


class RegistryStore(Protocol):
    """Minimal store contract reused from registry_builder storage adapters."""

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...


StoreFactory = Callable[[dict[str, Any]], RegistryStore]


def _matches_filter(row: dict[str, Any], filt: dict[str, Any]) -> bool:
    for key, expected in (filt or {}).items():
        if row.get(key) != expected:
            return False
    return True


def _is_current(row: dict[str, Any]) -> bool:
    """Return True unless registry-builder explicitly marked a format inactive."""
    return row.get("current") is not False


def _claim_is_institution_scoped(row: dict[str, Any]) -> bool:
    if row.get("institution_id"):
        return True
    return str(row.get("source_independence") or "").lower() == "institution_scoped"


def _claim_matches_scope(row: dict[str, Any], *, institution_id: str | None) -> bool:
    if not institution_id:
        return not _claim_is_institution_scoped(row)
    if not _claim_is_institution_scoped(row):
        return True
    return str(row.get("institution_id") or "") == institution_id


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _append_unique(values: list[str], value: str | None) -> None:
    if not value:
        return
    if value not in values:
        values.append(value)


def _string_values(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _identifier_values(format_doc: dict[str, Any], kind: str) -> list[str]:
    values: list[str] = []
    direct_key = {
        "puid": "puids",
        "loc": "loc_ids",
        "nara": "nara_ids",
    }.get(kind)
    if direct_key:
        for value in _string_values(format_doc.get(direct_key)):
            _append_unique(values, value)

    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in _string_values(identifiers.get(kind)):
            _append_unique(values, value)
    elif isinstance(identifiers, list):
        for item in identifiers:
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "") != kind:
                continue
            for value in _string_values(item.get("value")):
                _append_unique(values, value)
    return values


def _puid_alias(value: str) -> str | None:
    normalized = value.strip().lower().replace("/", "-")
    if not normalized:
        return None
    if normalized.startswith("puid-"):
        return normalized
    return f"puid-{normalized}"


def _loc_alias(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("loc-"):
        return normalized
    return f"loc-{normalized}"


def _nara_alias(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("nara-"):
        return normalized
    return f"nara-{normalized}"


def _claim_dedupe_key(row: dict[str, Any]) -> str:
    if row.get("_storage_key"):
        return str(row["_storage_key"])
    parts = [
        row.get("canonical_id"),
        row.get("criterion_id"),
        row.get("source_id"),
        row.get("source_record_id"),
        row.get("mapping_rule_id"),
        row.get("institution_id"),
    ]
    return "|".join(str(part or "") for part in parts)


def load_storage_config(path: str | Path) -> dict[str, Any]:
    """Load a registry-builder storage config from JSON.

    The risk manager accepts either the storage block itself:

    {"type": "file", "path": "..."}

    or a full registry-builder pipeline config containing a top-level
    `storage` object. This keeps analysis pointed at the same evidence store used
    to build the registry without duplicating storage implementation here.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistryAccessError(f"Storage config {path} must contain a JSON object")
    storage = data.get("storage")
    if storage is None:
        return dict(data)
    if not isinstance(storage, dict):
        raise RegistryAccessError(f"Storage config {path} has non-object 'storage' value")
    return dict(storage)


class JsonRegistryStore:
    """Read a registry JSON export through the RegistryStore query contract."""

    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self.collections = collections

    @classmethod
    def from_registry_json(cls, path: str | Path) -> "JsonRegistryStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            canonical_formats = [item for item in data if isinstance(item, dict)]
            collections = {"canonical_formats": canonical_formats}
        elif isinstance(data, dict):
            rows = data.get("canonical_formats") or data.get("formats") or data.get("registry") or []
            if not isinstance(rows, list):
                raise RegistryAccessError(f"Registry JSON {path} does not contain a canonical format list")
            canonical_formats = [item for item in rows if isinstance(item, dict)]
            collections = {"canonical_formats": canonical_formats}
            for collection_name in ("criterion_claims", "format_evidence_claims"):
                collection_rows = data.get(collection_name)
                if isinstance(collection_rows, list):
                    collections[collection_name] = [item for item in collection_rows if isinstance(item, dict)]
        else:
            raise RegistryAccessError(f"Registry JSON {path} must be a list or object")
        return cls(collections)

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = self.collections.get(collection, [])
        filt = filt or {}
        return [row for row in rows if _matches_filter(row, filt)]


def create_store_from_registry_builder(storage_config: dict[str, Any]) -> RegistryStore:
    """Create a registry store through registry_builder.storage.create_store.

    This import is deliberately lazy so the standalone risk-manager tests do not
    require the sibling registry-builder package. Real registry integration can
    pass the same storage block used by qnl_format_registry_builder.
    """
    try:
        from registry_builder.storage import create_store  # type: ignore
    except ImportError as exc:
        raise RegistryAccessError(
            "registry_builder is not importable. Install qnl_format_registry_builder or pass an explicit store."
        ) from exc
    return create_store(storage_config)


class RegistryReader:
    """Read registry evidence through the generic RegistryStore query contract."""

    def __init__(
        self,
        *,
        store: RegistryStore | None = None,
        storage_config: dict[str, Any] | None = None,
        store_factory: StoreFactory | None = None,
    ) -> None:
        if store is None:
            if storage_config is None:
                raise RegistryAccessError("RegistryReader requires either a store or storage_config")
            factory = store_factory or create_store_from_registry_builder
            store = factory(storage_config)
        self.store = store

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return list(self.store.query(collection, filt or {}))

    def list_canonical_formats(self) -> list[dict[str, Any]]:
        return [row for row in self.query("canonical_formats", {}) if _is_current(row)]

    def get_canonical_format(self, canonical_id: str) -> dict[str, Any] | None:
        """Return one current canonical format by known ID field, or None."""
        for field in ("canonical_id", "format_id", "id"):
            rows = [row for row in self.query("canonical_formats", {field: canonical_id}) if _is_current(row)]
            if rows:
                return rows[0]
        return None

    def criterion_claim_canonical_ids(self, format_doc: dict[str, Any]) -> list[str]:
        """Return canonical IDs whose criterion claims may describe this format.

        The registry may carry an institution aggregate record such as fmt-pdf
        while source-generated criterion claims are attached to source-derived
        canonical records such as puid-fmt-18 or loc-fdd000030. Risk analysis
        should use strong identity aliases to collect those claims without using
        weak extension/MIME overlaps.
        """
        ids: list[str] = []
        for field in ("canonical_id", "format_id", "id"):
            value = format_doc.get(field)
            if value is not None:
                _append_unique(ids, str(value))

        for value in _identifier_values(format_doc, "puid"):
            _append_unique(ids, _puid_alias(value))
        for value in _identifier_values(format_doc, "loc"):
            _append_unique(ids, _loc_alias(value))
        for value in _identifier_values(format_doc, "nara"):
            _append_unique(ids, _nara_alias(value))
        return ids

    def get_criterion_claims(
        self,
        *,
        canonical_id: str,
        institution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return criterion claims for a format in the requested scope.

        Global analysis must not consume institution-scoped claims. Institution
        analysis gets global claims plus matching claims for that institution.
        """
        rows = self.query("criterion_claims", {"canonical_id": canonical_id})
        return [row for row in rows if _claim_matches_scope(row, institution_id=institution_id)]

    def get_criterion_claims_for_format(
        self,
        format_doc: dict[str, Any],
        *,
        institution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        seen: set[str] = set()
        for canonical_id in self.criterion_claim_canonical_ids(format_doc):
            for row in self.get_criterion_claims(canonical_id=canonical_id, institution_id=institution_id):
                key = _claim_dedupe_key(row)
                if key in seen:
                    continue
                seen.add(key)
                claims.append(row)
        return claims

    def get_format_evidence_claims(
        self,
        *,
        canonical_id: str,
        institution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read legacy format evidence claims, optionally scoped to an institution."""
        query: dict[str, Any] = {"canonical_id": canonical_id}
        if institution_id:
            query["institution_id"] = institution_id
        return self.query("format_evidence_claims", query)
