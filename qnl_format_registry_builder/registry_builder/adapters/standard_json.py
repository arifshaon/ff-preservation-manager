from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


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
          "institution_evidence": [],
          "evidence": []
        }
      ]
    }
    """

    type_name = "standard_json"

    def acquire(self) -> list[SourceSnapshot]:
        snapshots: list[SourceSnapshot] = []
        for uri in self.config.get("uris", []):
            suffix = Path(uri.split("?")[0]).suffix or ".json"
            snapshots.append(self.acquire_uri_snapshot(uri, suffix=suffix))
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
                    institution_evidence=record.get("institution_evidence", []) or record.get("institution_evidence_claims", []) or [],
                    hazard=record.get("hazard", {}) or {},
                    readiness=record.get("readiness", {}) or {},
                    trend=record.get("trend", {}) or {},
                    evidence=record.get("evidence", []) or [],
                    raw=record,
                ))
        return rows
