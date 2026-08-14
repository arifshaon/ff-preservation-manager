from __future__ import annotations

from typing import Any

from registry_builder.storage.base import RegistryStore


class MongoRegistryStore(RegistryStore):
    """MongoDB RegistryStore backend design stub.

    MongoDB is the first intended production backend for the live/queryable local
    registry. This stub documents the contract and keeps the code importable
    until the PyMongo implementation is added.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        raise NotImplementedError(
            "MongoRegistryStore is planned as the first production backend. "
            "Implement with PyMongo after the storage interface is accepted."
        )

    def create_run(self, run: dict[str, Any]) -> str:
        raise NotImplementedError

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_source_record(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        raise NotImplementedError

    def upsert_identifier(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_institution_policy_overlay(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_trend_observation(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def save_assessment_change(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_current_registry_view(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_institution_policy_formats(self, institution_id: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        raise NotImplementedError
