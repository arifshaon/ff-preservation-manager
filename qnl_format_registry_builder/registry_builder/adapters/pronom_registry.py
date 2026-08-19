from __future__ import annotations

import json
import re
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes

DEFAULT_PRONOM_TREE_URL = "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1"
DEFAULT_PRONOM_RAW_BASE = "https://raw.githubusercontent.com/nationalarchives/pronom/develop"
DEFAULT_PRONOM_ARCHIVE_URL = "https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip"
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


def _snapshot_is_archive(snapshot: SourceSnapshot) -> bool:
    content_type = (snapshot.content_type or "").lower()
    uri = (snapshot.uri or "").lower()
    path = Path(snapshot.local_path)
    return path.suffix.lower() == ".zip" or uri.endswith(".zip") or "zip" in content_type


def _archive_member_matches(path: str, include_paths: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    if not normalized.lower().endswith(".json"):
        return False
    if "signatures/" not in normalized:
        return False
    relative = "signatures/" + normalized.split("signatures/", 1)[1]
    return any(relative.startswith(prefix) for prefix in include_paths)


def _record_from_pronom_json(
    *,
    source_id: str,
    source_type: str,
    snapshot: SourceSnapshot,
    record: dict[str, Any],
    source_file: str,
    evidence_type: str,
) -> RawFormatRecord | None:
    puid = _first_identifier(record, "PUID")
    if not puid:
        match = re.search(r"/signatures/(fmt|x-fmt)/(\d+)\.json$", source_file.replace("\\", "/"))
        if match:
            puid = f"{match.group(1)}/{match.group(2)}"
    if not puid and not record.get("formatName"):
        return None

    urls = {}
    if puid:
        urls["pronom"] = f"https://pronom.nationalarchives.gov.uk/{puid}"
        if not _snapshot_is_archive(snapshot):
            urls["pronom_json"] = snapshot.uri

    evidence = {
        "type": evidence_type,
        "retrieval_mode": evidence_type.replace("pronom_registry_", ""),
        "source_file": source_file,
        "source_archive": snapshot.uri if _snapshot_is_archive(snapshot) else None,
        "snapshot_sha256": snapshot.sha256,
        "snapshot_changed": snapshot.changed,
        "snapshot_from_cache": snapshot.from_cache,
        "snapshot_policy": snapshot.metadata.get("snapshot_policy"),
        "snapshot_retained": snapshot.metadata.get("snapshot_retained", True),
        "last_updated_date": record.get("lastUpdatedDate"),
        "format_disclosure": record.get("formatDisclosure"),
        "format_risk": record.get("formatRisk"),
    }

    return RawFormatRecord(
        source_id=source_id,
        source_type=source_type,
        source_record_id=puid or str(record.get("fileFormatID") or source_file),
        name=record.get("formatName"),
        category=record.get("formatTypes"),
        description=record.get("formatDescription"),
        extensions=_external_signatures(record, "File extension"),
        mime_types=_identifiers(record, "MIME"),
        puids=[puid] if puid else [],
        urls=urls,
        evidence=[evidence],
        raw={"snapshot_sha256": snapshot.sha256, "source_file": source_file, "record": record},
    )


class PronomRegistryAdapter(SourceAdapter):
    """Acquire and parse PRONOM registry data from its GitHub JSON dataset.

    Full PRONOM runs can use `github_archive`, which snapshots one repository
    archive and extracts JSON records from it. Individual JSON mode remains
    supported and can use temporary per-record snapshots that are deleted after
    extraction while normalized source records are persisted through storage.
    """

    type_name = "pronom_registry"

    def _progress_enabled(self) -> bool:
        return bool(self.config.get("progress", True))

    def _progress_interval(self) -> int:
        try:
            return max(1, int(self.config.get("progress_interval", 100)))
        except (TypeError, ValueError):
            return 100

    def _progress(self, message: str) -> None:
        if self._progress_enabled():
            print(f"[pronom_registry] {message}", flush=True)

    def _include_paths(self) -> tuple[str, ...]:
        return tuple(self.config.get("include_paths") or DEFAULT_INCLUDE_PATHS)

    def _retrieval_mode(self) -> str:
        mode = self.config.get("retrieval_mode")
        if mode:
            return str(mode)
        if self.config.get("puids") or self.config.get("uris") or self.config.get("github_tree_url") or self.config.get("tree_url"):
            return "github_json"
        return "github_archive"

    def _snapshot_policy(self) -> str:
        """Return cache policy for individual JSON acquisition.

        `cache` keeps per-record snapshots in the content-addressed cache. This is
        useful for targeted PUID tests. `temporary` writes each downloaded JSON to
        a temporary file, extracts it, and deletes it after extraction. Tree-based
        full JSON runs default to `temporary` so they do not fill the cache with
        thousands of files.
        """
        if self.config.get("delete_after_extract") is True:
            return "temporary"
        configured = self.config.get("snapshot_policy") or self.config.get("cache_strategy")
        if configured:
            policy = str(configured).strip().lower()
            if policy in {"temporary", "transient", "delete", "delete_after_extract", "stream"}:
                return "temporary"
            if policy in {"cache", "cached", "retain", "retained"}:
                return "cache"
            raise ValueError(f"Unsupported PRONOM snapshot_policy/cache_strategy: {configured}")
        if self.config.get("github_tree_url") or self.config.get("tree_url"):
            return "temporary"
        return "cache"

    def _uris_from_tree(self) -> list[str]:
        tree_url = self.config.get("github_tree_url") or self.config.get("tree_url")
        if not tree_url:
            return []
        self._progress(f"Reading GitHub tree: {tree_url}")
        if self.offline:
            cached = self._cached_snapshot(uri=tree_url, suffix=".json", note="retrieval_mode=github_json_tree")
            if not cached:
                raise FileNotFoundError(
                    f"Offline mode requested but no cached PRONOM tree snapshot exists for {tree_url}"
                )
            data = Path(cached.local_path).read_bytes()
            self._progress("Using cached PRONOM tree snapshot")
        else:
            tree_snapshot = self.acquire_uri_snapshot(tree_url, suffix=".json", note="retrieval_mode=github_json_tree")
            data = Path(tree_snapshot.local_path).read_bytes()
            status = "changed" if tree_snapshot.changed else "unchanged"
            self._progress(f"GitHub tree snapshot acquired ({status})")
        raw_base_url = self.config.get("raw_base_url", DEFAULT_PRONOM_RAW_BASE)
        include_paths = self._include_paths()
        tree = json.loads(data.decode("utf-8"))
        uris: list[str] = []
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            if entry.get("type") != "blob" or not path.endswith(".json"):
                continue
            if not any(path.startswith(prefix) for prefix in include_paths):
                continue
            uris.append(f"{raw_base_url.rstrip('/')}/{path}")
        self._progress(f"Tree resolved to {len(uris)} PRONOM JSON records")
        return uris

    def _uris(self) -> list[str]:
        raw_base_url = self.config.get("raw_base_url", DEFAULT_PRONOM_RAW_BASE)
        uris: list[str] = list(self.config.get("uris", []))
        for puid in self.config.get("puids", []):
            uris.append(_puid_to_raw_url(puid, raw_base_url))
        uris.extend(self._uris_from_tree())
        if not uris:
            raise ValueError(
                "pronom_registry github_json mode requires one of: uris, puids, or github_tree_url. "
                "For full runs, prefer github_archive when available or github_json with snapshot_policy:temporary."
            )
        max_records = self.config.get("max_records")
        deduped = list(dict.fromkeys(uris))
        if max_records is not None:
            limited = deduped[: int(max_records)]
            self._progress(f"Applying max_records={max_records}; acquiring {len(limited)} of {len(deduped)} records")
            return limited
        return deduped

    def _temporary_snapshot_dir(self) -> Path:
        return ensure_dir(self.workdir / "temporary_snapshots" / self.source_id)

    def _acquire_temporary_uri_snapshot(self, uri: str, *, suffix: str, note: str | None = None) -> SourceSnapshot:
        data, headers = read_uri(uri)
        digest = sha256_bytes(data)
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        local_path = self._temporary_snapshot_dir() / f"{digest}{suffix}"
        local_path.write_bytes(data)
        return SourceSnapshot(
            source_id=self.source_id,
            source_type=self.type_name,
            uri=uri,
            acquired_at=utc_now_iso(),
            sha256=digest,
            local_path=str(local_path),
            content_type=headers.get("content-type"),
            note="; ".join(x for x in [note, "snapshot_policy=temporary", "delete_after_extract=true"] if x),
            changed=None,
            from_cache=False,
            metadata={
                "snapshot_policy": "temporary",
                "snapshot_retained": False,
                "delete_after_extract": True,
                "source_location": "remote_uri",
            },
        )

    def _delete_temporary_snapshot(self, snapshot: SourceSnapshot) -> None:
        if not snapshot.metadata.get("delete_after_extract"):
            return
        with suppress(FileNotFoundError):
            Path(snapshot.local_path).unlink()

    def _acquire_archive(self) -> list[SourceSnapshot]:
        archive_url = self.config.get("archive_url") or DEFAULT_PRONOM_ARCHIVE_URL
        self._progress(f"Acquiring PRONOM repository archive: {archive_url}")
        snapshot = self.acquire_uri_snapshot(
            archive_url,
            suffix=".zip",
            note="retrieval_mode=github_archive",
            metadata={"source_location": "pronom_github_archive", "snapshot_policy": "cache", "snapshot_retained": True},
        )
        status = "changed" if snapshot.changed else "unchanged"
        self._progress(f"PRONOM archive snapshot acquired ({status})")
        return [snapshot]

    def _acquire_json_uris(self) -> list[SourceSnapshot]:
        uris = self._uris()
        total = len(uris)
        interval = self._progress_interval()
        policy = self._snapshot_policy()
        if policy == "temporary":
            self._progress(f"Acquiring {total} PRONOM JSON records with temporary snapshots")
        else:
            self._progress(f"Acquiring {total} PRONOM JSON records with retained cache snapshots")
        snapshots: list[SourceSnapshot] = []
        for index, uri in enumerate(uris, start=1):
            if policy == "temporary":
                snapshot = self._acquire_temporary_uri_snapshot(uri, suffix=".json", note="retrieval_mode=github_json")
            else:
                snapshot = self.acquire_uri_snapshot(
                    uri,
                    suffix=".json",
                    note="retrieval_mode=github_json; snapshot_policy=cache",
                    metadata={"snapshot_policy": "cache", "snapshot_retained": True},
                )
            snapshots.append(snapshot)
            if index == 1 or index % interval == 0 or index == total:
                self._progress(f"Acquired {index}/{total} PRONOM JSON records")
        return snapshots

    inbox_hint = (
        "Drop the PRONOM GitHub archive ZIP here (e.g. develop.zip from "
        "github.com/digital-preservation/pronom), or individual PRONOM JSON "
        "records. A manifest.json with {\"published_at\": ..., \"edition\": ...} "
        "records which PRONOM release the archive represents."
    )

    def network_acquire(self) -> list[SourceSnapshot]:
        mode = self._retrieval_mode()
        if mode in {"github_archive", "archive", "zip"} or self.config.get("archive_url"):
            return self._acquire_archive()
        return self._acquire_json_uris()

    def _extract_archive(self, snapshot: SourceSnapshot) -> list[RawFormatRecord]:
        include_paths = self._include_paths()
        interval = self._progress_interval()
        max_records = self.config.get("max_records")
        max_records_int = int(max_records) if max_records is not None else None
        records: list[RawFormatRecord] = []
        with zipfile.ZipFile(Path(snapshot.local_path)) as archive:
            members = [name for name in sorted(archive.namelist()) if _archive_member_matches(name, include_paths)]
            if max_records_int is not None:
                self._progress(f"Applying max_records={max_records_int}; extracting {min(max_records_int, len(members))} of {len(members)} archive records")
                members = members[:max_records_int]
            total = len(members)
            self._progress(f"Extracting {total} PRONOM JSON records from one archive snapshot")
            for index, member in enumerate(members, start=1):
                record = json.loads(archive.read(member).decode("utf-8"))
                raw_record = _record_from_pronom_json(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    snapshot=snapshot,
                    record=record,
                    source_file=member,
                    evidence_type="pronom_registry_github_archive",
                )
                if raw_record:
                    records.append(raw_record)
                if index == 1 or index % interval == 0 or index == total:
                    self._progress(f"Extracted {index}/{total} PRONOM archive records")
        return records

    def _extract_json_snapshots(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        total = len(snapshots)
        interval = self._progress_interval()
        if total:
            self._progress(f"Extracting {total} PRONOM snapshots")
        for index, snap in enumerate(snapshots, start=1):
            try:
                record = json.loads(Path(snap.local_path).read_text(encoding="utf-8"))
                raw_record = _record_from_pronom_json(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    snapshot=snap,
                    record=record,
                    source_file=snap.uri,
                    evidence_type="pronom_registry_github_json",
                )
                if raw_record:
                    records.append(raw_record)
            finally:
                self._delete_temporary_snapshot(snap)
            if index == 1 or index % interval == 0 or index == total:
                self._progress(f"Extracted {index}/{total} PRONOM snapshots")
        return records

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snapshot in snapshots:
            if _snapshot_is_archive(snapshot):
                records.extend(self._extract_archive(snapshot))
            else:
                records.extend(self._extract_json_snapshots([snapshot]))
        return records
