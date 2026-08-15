from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from registry_builder.storage.base import RegistryStore

_COLLECTIONS = (
    "runs",
    "source_snapshots",
    "source_records",
    "canonical_formats",
    "format_identifiers",
    "institution_policy_overlays",
    "hazard_assessments",
    "readiness_assessments",
    "trend_observations",
    "assessment_changes",
    "criterion_claims",
)


def _document_key(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    if not text:
        return "record"
    if len(text) <= 120:
        return text
    return f"{text[:80]}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


class FileRegistryStore(RegistryStore):
    """JSON document RegistryStore backend.

    This is a real storage backend, not an export adapter. It persists the same
    logical collections as MongoRegistryStore, but stores each document as JSON
    under a collection directory. It is useful for local testing, review, and
    environments where MongoDB is not yet available.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.root = Path(
            self.config.get("path")
            or self.config.get("directory")
            or self.config.get("root")
            or "registry_store"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        for collection in _COLLECTIONS:
            self._collection_dir(collection).mkdir(parents=True, exist_ok=True)

    def _collection_dir(self, collection: str) -> Path:
        if collection not in _COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        return self.root / collection

    def _path(self, collection: str, key: str) -> Path:
        return self._collection_dir(collection) / f"{_safe_name(key)}.json"

    def _write(self, collection: str, key: str, record: dict[str, Any]) -> None:
        stored = _json_copy(record)
        stored.setdefault("_file_storage_key", key)
        self._path(collection, key).write_text(
            json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_collection(self, collection: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self._collection_dir(collection).glob("*.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def _read_one(self, collection: str, key: str) -> dict[str, Any] | None:
        path = self._path(collection, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def upsert(self, collection: str, key: str | None, doc: dict[str, Any]) -> str:
        key = str(key or _document_key(doc))
        self._write(collection, key, doc)
        return key

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        records = self._read_collection(collection)
        if filt:
            records = [record for record in records if all(record.get(k) == v for k, v in filt.items())]
        return records

    def create_run(self, run: dict[str, Any]) -> str:
        run_id = str(run.get("run_id") or run.get("id") or f"run-{_document_key(run)[:12]}")
        stored = deepcopy(run)
        stored["run_id"] = run_id
        self._write("runs", run_id, stored)
        return run_id

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            snapshot.get("run_id"),
            snapshot.get("source_id"),
            snapshot.get("sha256"),
        )) or _document_key(snapshot)
        self._write("source_snapshots", key, snapshot)

    def save_source_record(self, record: dict[str, Any]) -> None:
        source_record_id = record.get("source_record_id") or _document_key(record)
        stored = deepcopy(record)
        stored["source_record_id"] = source_record_id
        key = "|".join(str(x or "") for x in (
            stored.get("run_id"),
            stored.get("source_id"),
            source_record_id,
        ))
        self._write("source_records", key, stored)

    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        canonical_id = str(record.get("canonical_id") or record.get("format_id") or record.get("_id") or "")
        if not canonical_id:
            raise ValueError("canonical format record requires canonical_id")
        stored = deepcopy(record)
        stored["canonical_id"] = canonical_id
        stored["format_id"] = canonical_id
        self._write("canonical_formats", canonical_id, stored)
        return canonical_id

    def upsert_identifier(self, record: dict[str, Any]) -> None:
        format_id = record.get("format_id") or record.get("canonical_id")
        key = "|".join(str(x or "") for x in (
            format_id,
            record.get("type"),
            record.get("value"),
            record.get("source"),
        )) or _document_key(record)
        self._write("format_identifiers", key, record)

    def save_institution_policy_overlay(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("institution_id"),
            record.get("institution_format_id"),
            record.get("source_row"),
        )) or _document_key(record)
        self._write("institution_policy_overlays", key, record)

    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
        )) or _document_key(record)
        self._write("hazard_assessments", key, record)

    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("sequence", 0),
        )) or _document_key(record)
        self._write("readiness_assessments", key, record)

    def save_trend_observation(self, record: dict[str, Any]) -> None:
        key = "|".join(str(x or "") for x in (
            record.get("run_id"),
            record.get("format_id") or record.get("canonical_id"),
            record.get("sequence", 0),
        )) or _document_key(record)
        self._write("trend_observations", key, record)

    def save_assessment_change(self, record: dict[str, Any]) -> None:
        stored = deepcopy(record)
        stored.setdefault("change_id", _document_key(stored))
        self._write("assessment_changes", str(stored["change_id"]), stored)

    def get_current_registry_view(self) -> list[dict[str, Any]]:
        records = [
            record
            for record in self._read_collection("canonical_formats")
            if record.get("current", True) is not False
        ]
        return sorted(records, key=lambda x: str(x.get("preferred_name") or "").lower())

    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        for identifier in self._read_collection("format_identifiers"):
            if identifier.get("type") == identifier_type and identifier.get("value") == value:
                format_id = identifier.get("format_id") or identifier.get("canonical_id")
                if format_id:
                    record = self._read_one("canonical_formats", str(format_id))
                    if record and record.get("current", True) is not False:
                        return record
        return None

    def list_institution_policy_formats(self, institution_id: str | None = None) -> list[dict[str, Any]]:
        ids = set()
        for overlay in self._read_collection("institution_policy_overlays"):
            if institution_id and overlay.get("institution_id") != institution_id:
                continue
            format_id = overlay.get("format_id") or overlay.get("canonical_id")
            if format_id:
                ids.add(str(format_id))
        records = []
        for format_id in sorted(ids):
            record = self._read_one("canonical_formats", format_id)
            if record and record.get("current", True) is not False:
                records.append(record)
        return records

    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._read_collection("assessment_changes")
            if str(record.get("created_at", "")) > since
        ]
