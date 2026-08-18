from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from typing import Any

from registry_builder.storage.base import RegistryStore


def _document_key(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mongo_safe(value: Any) -> Any:
    """Return a Mongo-safe copy of a JSON-like value.

    Source records can contain upstream field names such as `docs.fileformat.com`.
    MongoDB versions differ in how comfortably they handle dots and leading `$`
    in field names, so the store normalizes keys before persistence. This is a
    storage concern only; source adapters and reconciliation should not know
    about MongoDB key rules.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).replace(".", "\uff0e")
            if text.startswith("$"):
                text = "\uff04" + text[1:]
            out[text] = _mongo_safe(item)
        return out
    if isinstance(value, list):
        return [_mongo_safe(item) for item in value]
    return value


class MongoRegistryStore(RegistryStore):
    """MongoDB RegistryStore backend.

    This is the first production storage backend. The pipeline writes direct
    in-memory objects to this store; JSON/CSV/SQLite/Markdown files are optional
    exports and are not used as staging files for MongoDB.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config or {}
        try:
            from pymongo import MongoClient, ASCENDING
        except ImportError as exc:  # pragma: no cover - exercised only without optional dependency
            raise RuntimeError(
                "MongoRegistryStore requires pymongo. Install with: "
                "python -m pip install -e '.[mongo]'"
            ) from exc

        self._ASCENDING = ASCENDING
        uri = self.config.get("uri", "mongodb://localhost:27017")
        database = self.config.get("database") or self.config.get("db") or "format_registry"
        timeout_ms = int(self.config.get("server_selection_timeout_ms", 5000))
        self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        if self.config.get("ping", True):
            self.client.admin.command("ping")
        self.db = self.client[database]
        self.prefix = str(self.config.get("collection_prefix", "")).strip()
        self._ensure_indexes()

    def _name(self, collection: str) -> str:
        return f"{self.prefix}{collection}" if self.prefix else collection

    def _collection(self, collection: str):
        return self.db[self._name(collection)]

    def _replace(self, collection: str, filter_doc: dict[str, Any], record: dict[str, Any]) -> None:
        self._collection(collection).replace_one(_mongo_safe(filter_doc), _mongo_safe(record), upsert=True)

    def _insert(self, collection: str, record: dict[str, Any]) -> None:
        self._collection(collection).insert_one(_mongo_safe(record))

    def upsert(self, collection: str, key: str | None, doc: dict[str, Any]) -> str:
        key = str(key or _document_key(doc))
        stored = deepcopy(doc)
        stored.setdefault("_storage_key", key)
        self._replace(collection, {"_storage_key": key}, stored)
        return key

    def query(self, collection: str, filt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._collection(collection).find(_mongo_safe(filt or {}), {"_id": 0})
        return [dict(item) for item in cursor]

    def close(self) -> None:
        self.client.close()

    def _ensure_indexes(self) -> None:
        A = self._ASCENDING
        indexes = {
            "runs": [[("run_id", A)]],
            "source_snapshots": [[("run_id", A), ("source_id", A), ("sha256", A)]],
            "source_records": [[("run_id", A), ("source_id", A), ("source_record_id", A)]],
            "canonical_formats": [[("canonical_id", A)], [("preferred_name", A)], [("current", A)]],
            "format_identifiers": [[("type", A), ("value", A)], [("format_id", A), ("type", A), ("value", A)]],
            "institution_policy_overlays": [[("run_id", A), ("format_id", A)], [("institution_id", A), ("institution_format_id", A)]],
            "hazard_assessments": [[("run_id", A), ("format_id", A)], [("basis", A), ("band", A)]],
            "readiness_assessments": [[("run_id", A), ("format_id", A)]],
            "trend_observations": [[("run_id", A), ("format_id", A)]],
            "assessment_changes": [[("created_at", A)], [("format_id", A)], [("change_type", A)]],
            "criterion_claims": [
                [("canonical_id", A), ("criterion_id", A)],
                [("source_id", A), ("mapping_rule_id", A)],
                [("criteria_version", A), ("mapping_version", A)],
                [("institution_id", A)],
            ],
        }
        for collection, collection_indexes in indexes.items():
            coll = self._collection(collection)
            for keys in collection_indexes:
                coll.create_index(keys)

    def create_run(self, run: dict[str, Any]) -> str:
        run_id = str(run.get("run_id") or run.get("id") or f"run-{_document_key(run)[:12]}")
        stored = deepcopy(run)
        stored["run_id"] = run_id
        self._replace("runs", {"run_id": run_id}, stored)
        return run_id

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        key = {
            "run_id": snapshot.get("run_id"),
            "source_id": snapshot.get("source_id"),
            "sha256": snapshot.get("sha256"),
        }
        self._replace("source_snapshots", key, snapshot)

    def save_source_record(self, record: dict[str, Any]) -> None:
        source_record_id = record.get("source_record_id") or _document_key(record)
        stored = deepcopy(record)
        stored["source_record_id"] = source_record_id
        key = {
            "run_id": stored.get("run_id"),
            "source_id": stored.get("source_id"),
            "source_record_id": source_record_id,
        }
        self._replace("source_records", key, stored)

    def upsert_canonical_format(self, record: dict[str, Any]) -> str:
        canonical_id = str(record.get("canonical_id") or record.get("format_id") or record.get("_id") or "")
        if not canonical_id:
            raise ValueError("canonical format record requires canonical_id")
        stored = deepcopy(record)
        stored["canonical_id"] = canonical_id
        stored["format_id"] = canonical_id
        self._replace("canonical_formats", {"canonical_id": canonical_id}, stored)
        return canonical_id

    def upsert_identifier(self, record: dict[str, Any]) -> None:
        format_id = record.get("format_id") or record.get("canonical_id")
        key = {
            "format_id": format_id,
            "type": record.get("type"),
            "value": record.get("value"),
            "source": record.get("source"),
        }
        self._replace("format_identifiers", key, record)

    def save_institution_policy_overlay(self, record: dict[str, Any]) -> None:
        key = {
            "run_id": record.get("run_id"),
            "format_id": record.get("format_id") or record.get("canonical_id"),
            "institution_id": record.get("institution_id"),
            "institution_format_id": record.get("institution_format_id"),
            "source_row": record.get("source_row"),
        }
        self._replace("institution_policy_overlays", key, record)

    def save_hazard_assessment(self, record: dict[str, Any]) -> None:
        key = {
            "run_id": record.get("run_id"),
            "format_id": record.get("format_id") or record.get("canonical_id"),
        }
        self._replace("hazard_assessments", key, record)

    def save_readiness_assessment(self, record: dict[str, Any]) -> None:
        key = {
            "run_id": record.get("run_id"),
            "format_id": record.get("format_id") or record.get("canonical_id"),
            "sequence": record.get("sequence", 0),
        }
        self._replace("readiness_assessments", key, record)

    def save_trend_observation(self, record: dict[str, Any]) -> None:
        key = {
            "run_id": record.get("run_id"),
            "format_id": record.get("format_id") or record.get("canonical_id"),
            "sequence": record.get("sequence", 0),
        }
        self._replace("trend_observations", key, record)

    def save_assessment_change(self, record: dict[str, Any]) -> None:
        stored = deepcopy(record)
        stored.setdefault("change_id", _document_key(stored))
        self._replace("assessment_changes", {"change_id": stored["change_id"]}, stored)

    def get_current_registry_view(self) -> list[dict[str, Any]]:
        cursor = self._collection("canonical_formats").find(
            {"current": {"$ne": False}}, {"_id": 0}
        ).sort("preferred_name", self._ASCENDING)
        return [dict(item) for item in cursor]

    def find_by_identifier(self, identifier_type: str, value: str) -> dict[str, Any] | None:
        """Resolve against the current canonical identity index.

        `format_identifiers` is retained as provenance/history and can contain
        identifier claims written by older runs. Current identity is defined by
        `canonical_formats.identifiers`, which is rebuilt atomically and excludes
        copied/unverified strong cross-references.
        """
        kind = str(identifier_type or "").strip()
        needle = str(value or "").strip()
        if not kind or not needle:
            return None
        result = self._collection("canonical_formats").find_one(
            {
                f"identifiers.{kind}": needle,
                "current": {"$ne": False},
            },
            {"_id": 0},
        )
        return dict(result) if result else None

    def list_institution_policy_formats(self, institution_id: str | None = None) -> list[dict[str, Any]]:
        query = {"institution_id": institution_id} if institution_id else {}
        format_ids = [
            x for x in self._collection("institution_policy_overlays").distinct("format_id", query) if x
        ]
        cursor = self._collection("canonical_formats").find(
            {"canonical_id": {"$in": format_ids}, "current": {"$ne": False}}, {"_id": 0}
        )
        return [dict(item) for item in cursor]

    def list_changes_since(self, since: str) -> list[dict[str, Any]]:
        cursor = self._collection("assessment_changes").find({"created_at": {"$gt": since}}, {"_id": 0})
        return [dict(item) for item in cursor]
