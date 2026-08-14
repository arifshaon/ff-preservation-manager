from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes

DEFAULT_PRONOM_TREE_URL = "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1"
DEFAULT_PRONOM_RAW_BASE = "https://raw.githubusercontent.com/nationalarchives/pronom/develop"
DEFAULT_INCLUDE_PATHS = ("signatures/fmt/", "signatures/x-fmt/")


def _puid_to_raw_url(puid: str, raw_base_url: str = DEFAULT_PRONOM_RAW_BASE) -> str:
    match = re.match(r"^(fmt|x-fmt)/(\d+)$", puid.strip(), flags=re.I)
    if not match:
        raise ValueError(f"Invalid PRONOM PUID for GitHub JSON retrieval: {puid}")
    kind, number = match.groups()
    return f"{raw_base_url.rstrip('/')}/signatures/{kind.lower()}/{number}.json"


def _first_identifier(record: dict[str, Any], identifier_type: str) -> str | None:
    for identifier in record.get("identifiers", []) or []:
        if str(identifier.get("identifierType", "")).lower() == identifier_type.lower():
            value = identifier.get("identifierText")
            if value:
                return str(value).strip()
    return None


def _identifiers(record: dict[str, Any], identifier_type: str) -> list[str]:
    out: list[str] = []
    for identifier in record.get("identifiers", []) or []:
        if str(identifier.get("identifierType", "")).lower() == identifier_type.lower():
            value = identifier.get("identifierText")
            if value:
                out.append(str(value).strip())
    return out


def _external_signatures(record: dict[str, Any], signature_type: str) -> list[str]:
    out: list[str] = []
    for signature in record.get("externalSignatures", []) or []:
        if str(signature.get("signatureType", "")).lower() == signature_type.lower():
            value = signature.get("externalSignature")
            if value:
                out.append(str(value).strip())
    return out


class PronomRegistryAdapter(SourceAdapter):
    """Acquire and parse PRONOM registry data from its GitHub JSON dataset.

    This is a source-level adapter. Its current implemented retrieval mode is
    `github_json`: it can fetch explicitly configured PUIDs, raw JSON URLs, or a
    recursive GitHub tree listing from the public PRONOM repository. It does not
    scrape PRONOM web pages.
    """

    type_name = "pronom_registry"

    def _uris_from_tree(self) -> list[str]:
        tree_url = self.config.get("github_tree_url") or self.config.get("tree_url")
        if not tree_url:
            return []
        raw_base_url = self.config.get("raw_base_url", DEFAULT_PRONOM_RAW_BASE)
        include_paths = tuple(self.config.get("include_paths") or DEFAULT_INCLUDE_PATHS)
        data, _headers = read_uri(tree_url)
        tree = json.loads(data.decode("utf-8"))
        uris: list[str] = []
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            if entry.get("type") != "blob" or not path.endswith(".json"):
                continue
            if not any(path.startswith(prefix) for prefix in include_paths):
                continue
            uris.append(f"{raw_base_url.rstrip('/')}/{path}")
        return uris

    def _uris(self) -> list[str]:
        raw_base_url = self.config.get("raw_base_url", DEFAULT_PRONOM_RAW_BASE)
        uris: list[str] = list(self.config.get("uris", []))
        for puid in self.config.get("puids", []):
            uris.append(_puid_to_raw_url(puid, raw_base_url))
        uris.extend(self._uris_from_tree())
        if not uris:
            raise ValueError(
                "pronom_registry requires one of: uris, puids, or github_tree_url. "
                "Use github_tree_url for the full GitHub JSON dataset, or puids for a targeted run."
            )
        max_records = self.config.get("max_records")
        deduped = list(dict.fromkeys(uris))
        if max_records is not None:
            return deduped[: int(max_records)]
        return deduped

    def acquire(self) -> list[SourceSnapshot]:
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        snapshots: list[SourceSnapshot] = []
        for uri in self._uris():
            data, headers = read_uri(uri)
            digest = sha256_bytes(data)
            local_path = snapshot_dir / f"{digest}.json"
            local_path.write_bytes(data)
            snapshots.append(SourceSnapshot(
                source_id=self.source_id,
                source_type=self.type_name,
                uri=uri,
                acquired_at=utc_now_iso(),
                sha256=digest,
                local_path=str(local_path),
                content_type=headers.get("content-type"),
                note="retrieval_mode=github_json",
            ))
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snap in snapshots:
            record = json.loads(Path(snap.local_path).read_text(encoding="utf-8"))
            puid = _first_identifier(record, "PUID")
            if not puid:
                match = re.search(r"/signatures/(fmt|x-fmt)/(\d+)\.json$", snap.uri)
                if match:
                    puid = f"{match.group(1)}/{match.group(2)}"
            if not puid and not record.get("formatName"):
                continue

            urls = {}
            if puid:
                urls["pronom"] = f"https://pronom.nationalarchives.gov.uk/{puid}"
                urls["pronom_json"] = snap.uri

            records.append(RawFormatRecord(
                source_id=self.source_id,
                source_type=self.type_name,
                source_record_id=puid or str(record.get("fileFormatID") or snap.uri),
                name=record.get("formatName"),
                category=record.get("formatTypes"),
                description=record.get("formatDescription"),
                extensions=_external_signatures(record, "File extension"),
                mime_types=_identifiers(record, "MIME"),
                puids=[puid] if puid else [],
                urls=urls,
                evidence=[{
                    "type": "pronom_registry_github_json",
                    "retrieval_mode": "github_json",
                    "source_file": snap.uri,
                    "snapshot_sha256": snap.sha256,
                    "last_updated_date": record.get("lastUpdatedDate"),
                    "format_disclosure": record.get("formatDisclosure"),
                    "format_risk": record.get("formatRisk"),
                }],
                raw={"snapshot_sha256": snap.sha256, "record": record},
            ))
        return records
