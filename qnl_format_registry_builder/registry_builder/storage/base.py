from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RegistryStore(ABC):
    """Storage backend interface for the queryable local registry.

    Pipeline and services should depend on this interface rather than a concrete
    database implementation. MongoDB is the first production backend, but later
    PostgreSQL, MySQL, SQLite, or file-backed implementations should be able to
    implement the same contract.
    """

    @abstractmethod
    def create_run(self, run: dict[str, Any]) -> str:
        """Create a pipeline run record and return its run id."""

    @abstractmethod
    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Persist acquired source snapshot metadata."""

    @abstractmethod
    def save_source_record(self, record: dict[str, Any]) -> None:
        """Persist a source record containing raw and normalized payloads."""

    @abstractmethod
    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        """Create or update a canonical format record and return its id."""

    @abstractmethod
    def upsert_identifier(self, record: dict[str, Any]) -> None:
        """Create or update a format identifier record."""

    @abstractmethod
    def save_qnl_policy_overlay(self, record: dict[str, Any]) -> None:
        """Persist QNL-specific policy overlay data."""

    @abstractmethod
    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        """Persist intrinsic format hazard assessment data."""

    @abstractmethod
    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        """Persist QNL readiness/coverage assessment data."""

    @abstractmethod
    def save_trend_observation(self, record: dict[str, Any]) -> None:
        """Persist trend evidence or an insufficient-evidence observation."""

    @abstractmethod
    def save_assessment_change(self, record: dict[str, Any]) -> None:
        """Persist change events and recommended actions."""

    @abstractmethod
    def get_current_registry_view(self) -> list[dict[str, Any]]:
        """Return a materialized current registry view for queries/exports."""

    @abstractmethod
    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        """Find a canonical format by identifier."""

    @abstractmethod
    def list_qnl_policy_formats(self) -> list[dict[str, Any]]:
        """Return formats with an attached QNL policy overlay."""

    @abstractmethod
    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        """Return assessment changes created after the supplied timestamp."""
