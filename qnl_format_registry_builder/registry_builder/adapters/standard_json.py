from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes


class StandardJsonAdapter(SourceAdapter):
    """Adapter for manually curated or tool-generated source packages.

    Expected input:
    {
      "records": [
        {
          "name": "PDF/A",
          "extensions": ["pdf"],
          "identifiers": {"puid": ["fmt/95"], "loc": ["fdd000125"]},
          "urls": {"loc": "https://..."},
          "hazard": {"external_band": "Low"},
          "institution_policy": {},
          "evidence": []
        }
      ]
    }
    """

    type_name = "standard_json"

    def acquire(self) -> list[SourceSnapshot]:
        snapshots: list[SourceSnapshot] = []
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        for uri in self.config.get("uris", []):
            data, headers = read_uri(uri)
            digest = sha256_bytes(data)
            suffix = Path(uri.split("?")[0]).suffix or ".json"
            local_path = snapshot_dir / f"{digest}{suffix}"
            local_path.write_bytes(data)
            snapshots.append(SourceSnapshot(
                source_id=self.source_id,
                source_type=self.type_name,
                uri=uri,
                acquired_at=utc_now_iso(),
                sha256=digest,
                local_path=str(local_path),
                content_type=headers.get("content-type"),
            ))
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        rows: list[RawFormatRecord] = []
        for snap in snapshots:
            package = json.loads(Path(snap.local_path).read_text(encoding="utf-8"))
            for i, record in enumerate(package.get("records", []), start=1):
                identifiers: dict[str, Any] = record.get("identifiers", {}) or {}
                institution_policy = (
                    record.get("institution_policy")
                    or record.get("institution_policy_overlay")
                    or record.get("qnl")
                    or {}
                )
                rows.append(RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id=record.get("source_record_id") or f"{self.source_id}:{i}",
                    name=record.get("name"),
                    category=record.get("category"),
                    description=record.get("description"),
                    extensions=list(identifiers.get("extension", []) or record.get("extensions", []) or []),
                    mime_types=list(identifiers.get("mime", []) or record.get("mime_types", []) or []),
                    puids=list(identifiers.get("puid", []) or record.get("puids", []) or []),
                    loc_ids=list(identifiers.get("loc", []) or record.get("loc_ids", []) or []),
                    nara_ids=list(identifiers.get("nara", []) or record.get("nara_ids", []) or []),
                    wikidata_ids=list(identifiers.get("wikidata", []) or record.get("wikidata_ids", []) or []),
                    urls=record.get("urls", {}) or {},
                    institution_policy=institution_policy,
                    hazard=record.get("hazard", {}) or {},
                    readiness=record.get("readiness", {}) or {},
                    trend=record.get("trend", {}) or {},
                    evidence=record.get("evidence", []) or [],
                    raw=record,
                ))
        return rows
