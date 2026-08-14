from __future__ import annotations

from copy import deepcopy
from typing import Any

from registry_builder.storage.base import RegistryStore


class MemoryRegistryStore(RegistryStore):
    """In-memory RegistryStore implementation for tests and local dry runs.

    This is not intended as a production registry. It exists so pipeline logic can
    be tested without MongoDB and so future storage implementations can be
    validated against the same interface.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.snapshots: list[dict[str, Any]] = []
        self.source_records: list[dict[str, Any]] = []
        self.canonical_formats: dict[str, dict[str, Any]] = {}
        self.identifiers: list[dict[str, Any]] = []
        self.institution_policy_overlays: list[dict[str, Any]] = []
        self.hazard_assessments: list[dict[str, Any]] = []
        self.readiness_assessments: list[dict[str, Any]] = []
        self.trend_observations: list[dict[str, Any]] = []
        self.assessment_changes: list[dict[str, Any]] = []

    def create_run(self, run: dict[str, Any]) -> str:
        run_id = str(run.get("run_id") or run.get("id") or f"run-{len(self.runs) + 1}")
        stored = deepcopy(run)
        stored["run_id"] = run_id
        self.runs[run_id] = stored
        return run_id

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.snapshots.append(deepcopy(snapshot))

    def save_source_record(self, record: dict[str, Any]) -> None:
        self.source_records.append(deepcopy(record))

    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        canonical_id = str(record.get("canonical_id") or record.get("format_id") or record.get("_id"))
        if not canonical_id or canonical_id == "None":
            raise ValueError("canonical format record requires canonical_id")
        stored = deepcopy(record)
        stored["canonical_id"] = canonical_id
        self.canonical_formats[canonical_id] = stored
        return canonical_id

    def upsert_identifier(self, record: dict[str, Any]) -> None:
        key = (record.get("format_id") or record.get("canonical_id"), record.get("type"), record.get("value"))
        for idx, existing in enumerate(self.identifiers):
            existing_key = (existing.get("format_id") or existing.get("canonical_id"), existing.get("type"), existing.get("value"))
            if existing_key == key:
                self.identifiers[idx] = deepcopy(record)
                return
        self.identifiers.append(deepcopy(record))

    def save_institution_policy_overlay(self, record: dict[str, Any]) -> None:
        self.institution_policy_overlays.append(deepcopy(record))

    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        self.hazard_assessments.append(deepcopy(record))

    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        self.readiness_assessments.append(deepcopy(record))

    def save_trend_observation(self, record: dict[str, Any]) -> None:
        self.trend_observations.append(deepcopy(record))

    def save_assessment_change(self, record: dict[str, Any]) -> None:
        self.assessment_changes.append(deepcopy(record))

    def get_current_registry_view(self) -> list[dict[str, Any]]:
        return [
            deepcopy(v)
            for v in self.canonical_formats.values()
            if v.get("current", True) is not False
        ]

    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        for identifier in self.identifiers:
            if identifier.get("type") == identifier_type and identifier.get("value") == value:
                format_id = identifier.get("format_id") or identifier.get("canonical_id")
                if format_id in self.canonical_formats:
                    record = self.canonical_formats[format_id]
                    if record.get("current", True) is not False:
                        return deepcopy(record)
        return None

    def list_institution_policy_formats(self, institution_id: str | None = None) -> list[dict[str, Any]]:
        ids = set()
        for overlay in self.institution_policy_overlays:
            if institution_id and overlay.get("institution_id") != institution_id:
                continue
            ids.add(overlay.get("format_id") or overlay.get("canonical_id"))
        return [
            deepcopy(v)
            for k, v in self.canonical_formats.items()
            if k in ids and v.get("current", True) is not False
        ]

    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        return [deepcopy(x) for x in self.assessment_changes if str(x.get("created_at", "")) > since]
