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

    inbox_hint = (
        "Drop standard-JSON package file(s) here ({\"records\": [...]}). Use "
        "manifest.json or per-file sidecars to record publication dates."
    )

    def network_acquire(self) -> list[SourceSnapshot]:
        snapshots: list[SourceSnapshot] = []
        for uri in self.config.get("uris", []):
            suffix = Path(uri.split("?")[0]).suffix or ".json"
            snapshots.append(self.acquire_uri_snapshot(uri, suffix=suffix))
        return snapshots

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        """Accept a scalar or a list for an identifier field.

        A hand-written package naturally says {"puid": "fmt/18"}. Passing that
        straight to list() silently yields ['f','m','t','/','1','8'] — six junk
        identifiers rather than one real one, with no error to notice.
        """
        if value is None or value == "":
            return []
        if isinstance(value, (str, bytes)):
            return [value.decode() if isinstance(value, bytes) else value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if item not in (None, "")]
        return [str(value)]

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
                    extensions=self._as_list(identifiers.get("extension")) or self._as_list(record.get("extensions")),
                    mime_types=self._as_list(identifiers.get("mime")) or self._as_list(record.get("mime_types")),
                    puids=self._as_list(identifiers.get("puid")) or self._as_list(record.get("puids")),
                    loc_ids=self._as_list(identifiers.get("loc")) or self._as_list(record.get("loc_ids")),
                    nara_ids=self._as_list(identifiers.get("nara")) or self._as_list(record.get("nara_ids")),
                    wikidata_ids=self._as_list(identifiers.get("wikidata")) or self._as_list(record.get("wikidata_ids")),
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
