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


def _read_collection_rows(path: Path, *, collection_name: str) -> list[dict[str, Any]]:
    """Read a JSON/JSONL collection export into row dictionaries."""
    if not path.is_file():
        raise RegistryAccessError(f"Collection export not found: {path.resolve(strict=False)}")

    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RegistryAccessError(f"Invalid JSONL in {path} at line {line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise RegistryAccessError(f"{path} line {line_number} must contain a JSON object")
            rows.append(item)
        return rows

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryAccessError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        candidate = data.get(collection_name) or data.get("rows") or data.get("items")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    raise RegistryAccessError(f"{path} does not contain a {collection_name} row list")


def _merge_claim_rows(existing: list[dict[str, Any]], additional: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [*existing, *additional]:
        key = _claim_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


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
    """Read registry-builder exports through the RegistryStore query contract."""

    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self.collections = collections

    @classmethod
    def from_registry_json(
        cls,
        path: str | Path,
        *,
        criterion_claims_path: str | Path | None = None,
    ) -> "JsonRegistryStore":
        """Load registry.json and the criterion-claim export that belongs with it.

        Registry-builder normally exports canonical formats to ``registry.json``
        and normalized claims to a sibling ``criterion_claims.jsonl`` (or JSON)
        file. Earlier risk-manager behavior loaded only registry.json, which made
        a documented file-export handoff silently lose the claims needed for risk
        assessment. The reader now auto-discovers the sibling claims export.

        ``criterion_claims_path`` can be supplied when claims live elsewhere.
        Embedded ``criterion_claims`` inside registry.json remain supported.
        """
        registry_path = Path(path)
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            canonical_formats = [item for item in data if isinstance(item, dict)]
            collections: dict[str, list[dict[str, Any]]] = {"canonical_formats": canonical_formats}
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

        claims_export: Path | None = None
        if criterion_claims_path is not None:
            claims_export = Path(criterion_claims_path)
        else:
            for candidate_name in ("criterion_claims.jsonl", "criterion_claims.json"):
                candidate = registry_path.parent / candidate_name
                if candidate.is_file():
                    claims_export = candidate
                    break

        if claims_export is not None:
            additional_claims = _read_collection_rows(claims_export, collection_name="criterion_claims")
            collections["criterion_claims"] = _merge_claim_rows(
                collections.get("criterion_claims", []),
                additional_claims,
            )

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
