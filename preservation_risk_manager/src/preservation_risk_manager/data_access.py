from __future__ import annotations

from typing import Any, Callable, Protocol

from preservation_risk_manager.errors import PreservationRiskManagerError


class RegistryAccessError(PreservationRiskManagerError):
    """Raised when registry evidence cannot be accessed through the reader."""


class RegistryStore(Protocol):
    """Minimal store contract reused from registry_builder storage adapters."""

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...


StoreFactory = Callable[[dict[str, Any]], RegistryStore]


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
        return self.query("canonical_formats", {})

    def get_canonical_format(self, canonical_id: str) -> dict[str, Any] | None:
        """Return one canonical format by known ID field, or None."""
        for field in ("canonical_id", "format_id", "id"):
            rows = self.query("canonical_formats", {field: canonical_id})
            if rows:
                return rows[0]
        return None

    def get_format_evidence_claims(
        self,
        *,
        canonical_id: str,
        institution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read format evidence claims, optionally scoped to an institution.

        This anticipates the optimized collection, but does not require it. If a
        store has no matching collection/index, it should simply return an empty
        list according to the generic query contract.
        """
        query: dict[str, Any] = {"canonical_id": canonical_id}
        if institution_id:
            query["institution_id"] = institution_id
        return self.query("format_evidence_claims", query)
