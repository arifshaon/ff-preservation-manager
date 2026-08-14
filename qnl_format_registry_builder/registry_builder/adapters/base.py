from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes


class SourceAdapter(ABC):
    type_name: str = "base"

    def __init__(self, source_config: dict[str, Any], workdir: Path):
        self.config = source_config
        self.workdir = workdir
        self.source_id = source_config["id"]

    @property
    def offline(self) -> bool:
        return bool(self.config.get("offline", False))

    def snapshot_dir(self) -> Path:
        return ensure_dir(self.workdir / "snapshots" / self.source_id)

    def _snapshot_index_path(self) -> Path:
        return self.snapshot_dir() / ".snapshot_index.json"

    def _load_snapshot_index(self) -> dict[str, dict[str, Any]]:
        path = self._snapshot_index_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_snapshot_index(self, index: dict[str, dict[str, Any]]) -> None:
        path = self._snapshot_index_path()
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _cached_snapshot(
        self,
        *,
        uri: str,
        suffix: str,
        note: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot | None:
        index = self._load_snapshot_index()
        entry = index.get(uri)
        if not entry:
            return None
        local_path = Path(entry.get("local_path", ""))
        if not local_path.exists():
            return None
        cached_metadata = dict(entry.get("metadata") or {})
        if metadata:
            cached_metadata.update(metadata)
        return SourceSnapshot(
            source_id=self.source_id,
            source_type=self.type_name,
            uri=uri,
            acquired_at=entry.get("acquired_at") or utc_now_iso(),
            sha256=entry.get("sha256", ""),
            local_path=str(local_path),
            content_type=entry.get("content_type") or content_type,
            note="; ".join(x for x in [note, "cache=hit", "offline=true" if self.offline else "reused=true"] if x),
            changed=False,
            from_cache=True,
            metadata=cached_metadata,
        )

    def acquire_uri_snapshot(
        self,
        uri: str,
        *,
        suffix: str,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot:
        """Acquire one URI as a content-addressed source snapshot.

        Online mode still checks the upstream source, but it no longer rewrites an
        unchanged cached snapshot. Offline mode uses the source snapshot index and
        fails loudly if the requested URI has not been cached before.
        """
        metadata = dict(metadata or {})
        if self.offline:
            cached = self._cached_snapshot(uri=uri, suffix=suffix, note=note, metadata=metadata)
            if cached:
                return cached
            raise FileNotFoundError(
                f"Offline mode requested but no cached snapshot index entry exists for {self.source_id}: {uri}"
            )

        data, headers = read_uri(uri)
        digest = sha256_bytes(data)
        index = self._load_snapshot_index()
        previous = index.get(uri)
        changed = previous is None or previous.get("sha256") != digest
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        local_path = self.snapshot_dir() / f"{digest}{suffix}"
        if not local_path.exists() or sha256_bytes(local_path.read_bytes()) != digest:
            local_path.write_bytes(data)

        acquired_at = utc_now_iso()
        content_type = headers.get("content-type")
        index[uri] = {
            "uri": uri,
            "sha256": digest,
            "local_path": str(local_path),
            "content_type": content_type,
            "acquired_at": acquired_at,
            "source_type": self.type_name,
            "metadata": metadata,
        }
        self._write_snapshot_index(index)
        return SourceSnapshot(
            source_id=self.source_id,
            source_type=self.type_name,
            uri=uri,
            acquired_at=acquired_at,
            sha256=digest,
            local_path=str(local_path),
            content_type=content_type,
            note="; ".join(x for x in [note, "changed=true" if changed else "changed=false"] if x),
            changed=changed,
            from_cache=False,
            metadata=metadata,
        )

    def acquire_uri_snapshots(
        self,
        uris: list[str],
        *,
        suffix: str,
        note: str | None = None,
        metadata_by_uri: dict[str, dict[str, Any]] | None = None,
    ) -> list[SourceSnapshot]:
        metadata_by_uri = metadata_by_uri or {}
        return [
            self.acquire_uri_snapshot(
                uri,
                suffix=suffix,
                note=note,
                metadata=metadata_by_uri.get(uri),
            )
            for uri in uris
        ]

    @abstractmethod
    def acquire(self) -> list[SourceSnapshot]:
        """Retrieve or access source material and return immutable local snapshots."""

    @abstractmethod
    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        """Parse snapshots and return raw source records in the internal interchange model."""
