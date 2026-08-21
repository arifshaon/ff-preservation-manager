from __future__ import annotations

from copy import deepcopy
from typing import Any

from registry_builder.storage.base import RegistryStore

_COLLECTION_ATTRS = {
    "runs": "runs",
    "source_snapshots": "snapshots",
    "source_records": "source_records",
    "canonical_formats": "canonical_formats",
    "format_identifiers": "identifiers",
    "institution_policy_overlays": "institution_policy_overlays",
    "hazard_assessments": "hazard_assessments",
    "readiness_assessments": "readiness_assessments",
    "trend_observations": "trend_observations",
    "assessment_changes": "assessment_changes",
    "criterion_claims": "criterion_claims",
    "risk_assessment_claims": "risk_assessment_claims",
    "source_relationship_claims": "source_relationship_claims",
}


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
        self.criterion_claims: list[dict[str, Any]] = []
        self.risk_assessment_claims: list[dict[str, Any]] = []
        self.source_relationship_claims: list[dict[str, Any]] = []

    def upsert(self, collection: str, key: str | None, doc: dict[str, Any]) -> str:
        stored = deepcopy(doc)
        if collection in {"runs", "canonical_formats"}:
            if collection == "runs":
                key = key or stored.get("run_id") or stored.get("id")
                stored["run_id"] = str(key)
                self.runs[str(key)] = stored
                return str(key)
            key = key or stored.get("canonical_id") or stored.get("format_id")
            stored["canonical_id"] = str(key)
            self.canonical_formats[str(key)] = stored
            return str(key)
        attr = _COLLECTION_ATTRS.get(collection)
        if attr is None:
            raise ValueError(f"Unknown collection: {collection}")
        target = getattr(self, attr)
        if not isinstance(target, list):
            raise ValueError(f"Collection is not list-backed: {collection}")
        key = key or f"{collection}-{len(target) + 1}"
        stored.setdefault("_storage_key", key)
        for idx, existing in enumerate(target):
            if existing.get("_storage_key") == key:
                target[idx] = stored
                return str(key)
        target.append(stored)
        return str(key)

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        attr = _COLLECTION_ATTRS.get(collection)
        if attr is None:
            raise ValueError(f"Unknown collection: {collection}")
        target = getattr(self, attr)
        records = list(target.values()) if isinstance(target, dict) else list(target)
        if filt:
            records = [record for record in records if all(record.get(k) == v for k, v in filt.items())]
        return [deepcopy(record) for record in records]

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
        """Resolve current canonical identity, with a legacy-only fallback.

        Rebuilt canonical records carry an explicit ``identifiers`` index and
        that index is authoritative. Historical ``format_identifiers`` rows are
        consulted only for older/minimal canonical records that have no
        ``identifiers`` field at all, preserving the storage contract without
        allowing stale rows to override rebuilt identity.
        """
        kind = str(identifier_type or "").strip()
        needle = str(value or "").strip()
        if not kind or not needle:
            return None

        for record in self.canonical_formats.values():
            if record.get("current", True) is False:
                continue
            identifiers = record.get("identifiers") or {}
            values = identifiers.get(kind) if isinstance(identifiers, dict) else None
            if isinstance(values, (list, tuple, set)) and needle in {str(item) for item in values}:
                return deepcopy(record)

        for identifier in self.identifiers:
            if identifier.get("type") != kind or str(identifier.get("value") or "") != needle:
                continue
            format_id = identifier.get("format_id") or identifier.get("canonical_id")
            record = self.canonical_formats.get(str(format_id)) if format_id is not None else None
            if not record or record.get("current", True) is False:
                continue
            if "identifiers" in record:
                continue
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
