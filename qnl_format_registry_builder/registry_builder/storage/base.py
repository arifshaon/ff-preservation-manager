from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any


def _document_key(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RegistryStore(ABC):
    """Storage backend interface for the queryable local registry.

    New storage backends implement a small generic document contract: upsert and
    query. The named save/upsert helpers below are concrete convenience methods
    shared by backends. Existing backends may still override them for optimized
    indexes or storage-specific behavior.
    """

    @abstractmethod
    def upsert(self, collection: str, key: str | None, doc: dict[str, Any]) -> str:
        """Create or replace one document and return the storage key used."""

    @abstractmethod
    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return documents from a collection matching a simple equality filter."""

    def begin(self) -> None:
        """Optional lifecycle hook for transactional backends."""

    def close(self) -> None:
        """Optional lifecycle hook for connection-backed stores."""

    def create_run(self, run: dict[str, Any]) -> str:
        run_id = str(run.get("run_id") or run.get("id") or f"run-{_document_key(run)[:12]}")
        stored = dict(run)
        stored["run_id"] = run_id
        self.upsert("runs", run_id, stored)
        return run_id

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (snapshot.get("run_id"), snapshot.get("source_id"), snapshot.get("sha256")))
        self.upsert("source_snapshots", key or None, snapshot)

    def save_source_record(self, record: dict[str, Any]) -> None:
        source_record_id = record.get("source_record_id") or _document_key(record)
        stored = dict(record)
        stored["source_record_id"] = source_record_id
        key = "|".join(str(x or "") for x in (stored.get("run_id"), stored.get("source_id"), source_record_id))
        self.upsert("source_records", key or None, stored)

    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        canonical_id = str(record.get("canonical_id") or record.get("format_id") or record.get("_id") or "")
        if not canonical_id:
            raise ValueError("canonical format record requires canonical_id")
        stored = dict(record)
        stored["canonical_id"] = canonical_id
        stored["format_id"] = canonical_id
        return self.upsert("canonical_formats", canonical_id, stored)

    def upsert_identifier(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("format_id") or record.get("canonical_id"),
            record.get("type"),
            record.get("value"),
            record.get("source"),
        ))
        self.upsert("format_identifiers", key or None, record)

    def save_institution_policy_overlay(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("institution_id"),
            record.get("institution_format_id"),
            record.get("source_row"),
        ))
        self.upsert("institution_policy_overlays", key or None, record)

    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (record.get("run_id"), record.get("format_id") or record.get("canonical_id")))
        self.upsert("hazard_assessments", key or None, record)

    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("sequence", 0),
        ))
        self.upsert("readiness_assessments", key or None, record)

    def save_trend_observation(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("sequence", 0),
        ))
        self.upsert("trend_observations", key or None, record)

    def save_assessment_change(self, record: dict[str, Any]) -> None:
        stored = dict(record)
        stored.setdefault("change_id", _document_key(stored))
        self.upsert("assessment_changes", str(stored["change_id"]), stored)

    def get_current_registry_view(self) -> list[dict[str, Any]]:
        records = [record for record in self.query("canonical_formats") if record.get("current", True) is not False]
        return sorted(records, key=lambda x: str(x.get("preferred_name") or "").lower())

    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        for identifier in self.query("format_identifiers", {"type": identifier_type, "value": value}):
            format_id = identifier.get("format_id") or identifier.get("canonical_id")
            if not format_id:
                continue
            matches = self.query("canonical_formats", {"canonical_id": format_id})
            for record in matches:
                if record.get("current", True) is not False:
                    return record
        return None

    def list_institution_policy_formats(self, institution_id: str | None = None) -> list[dict[str, Any]]:
        filt = {"institution_id": institution_id} if institution_id else None
        ids = {
            overlay.get("format_id") or overlay.get("canonical_id")
            for overlay in self.query("institution_policy_overlays", filt)
            if overlay.get("format_id") or overlay.get("canonical_id")
        }
        return [
            record
            for record in self.query("canonical_formats")
            if record.get("canonical_id") in ids and record.get("current", True) is not False
        ]

    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        return [record for record in self.query("assessment_changes") if str(record.get("created_at", "")) > since]
