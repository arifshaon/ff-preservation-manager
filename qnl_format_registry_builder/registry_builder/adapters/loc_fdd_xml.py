from __future__ import annotations

from contextlib import suppress
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes

DEFAULT_LOC_FDD_XML_ZIP = "https://www.loc.gov/preservation/digital/formats/fddXML.zip"


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _text_by_names(root: ET.Element, names: set[str]) -> list[str]:
    out: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) in names and elem.text and elem.text.strip():
            out.append(elem.text.strip())
    return out


def _snapshot_is_zip(snapshot: SourceSnapshot) -> bool:
    content_type = (snapshot.content_type or "").lower()
    uri = (snapshot.uri or "").lower()
    local_path = Path(snapshot.local_path)
    return (
        local_path.suffix.lower() == ".zip"
        or uri.endswith(".zip")
        or "zip" in content_type
    )


def _xml_payloads(snapshot: SourceSnapshot) -> list[tuple[str, bytes]]:
    path = Path(snapshot.local_path)
    if _snapshot_is_zip(snapshot):
        payloads: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                if name.endswith("/") or not name.lower().endswith(".xml"):
                    continue
                payloads.append((name, zf.read(name)))
        return payloads
    return [(snapshot.uri, path.read_bytes())]


def _first_loc_id(root: ET.Element, text: str) -> str | None:
    loc_ids = _text_by_names(root, {"fddid", "fdd_id", "id"})
    loc_id = next((x for x in loc_ids if re.match(r"fdd\d{6}$", x, re.I)), None)
    if loc_id:
        return loc_id.lower()
    match = re.search(r"\bfdd\d{6}\b", text, flags=re.I)
    return match.group(0).lower() if match else None


def _record_from_xml(snapshot: SourceSnapshot, source_file: str, data: bytes) -> RawFormatRecord | None:
    text = data.decode("utf-8", errors="replace")
    root = ET.fromstring(text)
    loc_id = _first_loc_id(root, text)
    titles = _text_by_names(root, {"title", "shortname", "short_name", "name"})
    categories = _text_by_names(root, {"category", "type"})

    # Conservative regex fallbacks for common identifiers embedded in FDD text.
    puids = sorted({x.lower() for x in re.findall(r"\b(?:fmt|x-fmt)/\d+\b", text, flags=re.I)})
    wikidata = sorted({x.upper() for x in re.findall(r"\bQ\d{2,}\b", text, flags=re.I)})
    extensions = sorted({x.lower() for x in re.findall(r"\.([A-Za-z0-9]{1,12})\b", text)})
    name = titles[0] if titles else None
    if not loc_id and not name:
        return None

    loc_url = (
        f"https://www.loc.gov/preservation/digital/formats/fddXML/{loc_id}.xml"
        if loc_id
        else snapshot.uri
    )
    evidence_type = "loc_fdd_xml_zip" if _snapshot_is_zip(snapshot) else "loc_fdd_xml_text"
    snapshot_retained = snapshot.metadata.get("snapshot_retained", True)
    raw = {"snapshot_sha256": snapshot.sha256, "source_file": source_file}
    if not snapshot_retained:
        raw["xml_text"] = text

    return RawFormatRecord(
        source_id=snapshot.source_id,
        source_type=snapshot.source_type,
        source_record_id=loc_id or f"{snapshot.uri}#{source_file}",
        name=name,
        category=categories[0] if categories else None,
        extensions=extensions,
        puids=puids,
        loc_ids=[loc_id] if loc_id else [],
        wikidata_ids=wikidata,
        urls={"loc": loc_url, "loc_source": snapshot.uri},
        evidence=[{
            "type": evidence_type,
            "source_file": source_file,
            "source_archive": snapshot.uri if _snapshot_is_zip(snapshot) else None,
            "snapshot_sha256": snapshot.sha256,
            "snapshot_changed": snapshot.changed,
            "snapshot_from_cache": snapshot.from_cache,
            "snapshot_policy": snapshot.metadata.get("snapshot_policy"),
            "snapshot_retained": snapshot_retained,
        }],
        raw=raw,
    )


class LocFddXmlAdapter(SourceAdapter):
    """Acquire and parse Library of Congress FDD XML records.

    LOC's FDD XML is used here as sustainability evidence and identifiers. The
    adapter supports the official FDD XML ZIP as the default online acquisition
    mode, plus explicit XML/ZIP URIs and local XML directories for admin-staged
    runs. Individual URI mode can use temporary snapshots that are deleted after
    extraction while normalized source records are persisted through storage.
    """

    type_name = "loc_fdd_xml"

    def _progress_enabled(self) -> bool:
        return bool(self.config.get("progress", True))

    def _progress_interval(self) -> int:
        try:
            return max(1, int(self.config.get("progress_interval", 100)))
        except (TypeError, ValueError):
            return 100

    def _progress(self, message: str) -> None:
        if self._progress_enabled():
            print(f"[loc_fdd_xml] {message}", flush=True)

    def _snapshot_policy(self) -> str:
        if self.config.get("delete_after_extract") is True:
            return "temporary"
        configured = self.config.get("snapshot_policy") or self.config.get("cache_strategy")
        if configured:
            policy = str(configured).strip().lower()
            if policy in {"temporary", "transient", "delete", "delete_after_extract", "stream"}:
                return "temporary"
            if policy in {"cache", "cached", "retain", "retained"}:
                return "cache"
            raise ValueError(f"Unsupported LOC snapshot_policy/cache_strategy: {configured}")
        return "cache"

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

    def _acquire_zip_snapshot(self) -> list[SourceSnapshot]:
        uri = self.config.get("zip_uri") or self.config.get("uri") or DEFAULT_LOC_FDD_XML_ZIP
        self._progress(f"Acquiring LOC FDD XML ZIP: {uri}")
        snapshot = self.acquire_uri_snapshot(
            uri,
            suffix=".zip",
            note="retrieval_mode=fdd_xml_zip",
            metadata={"source_location": "loc_fdd_xml_zip", "snapshot_policy": "cache", "snapshot_retained": True},
        )
        status = "changed" if snapshot.changed else "unchanged"
        self._progress(f"LOC FDD XML ZIP snapshot acquired ({status})")
        return [snapshot]

    def _acquire_xml_uris(self, uris: list[str]) -> list[SourceSnapshot]:
        policy = self._snapshot_policy()
        total = len(uris)
        interval = self._progress_interval()
        mode_text = "temporary snapshots" if policy == "temporary" else "retained cache snapshots"
        self._progress(f"Acquiring {total} LOC FDD XML/ZIP URI(s) with {mode_text}")
        snapshots: list[SourceSnapshot] = []
        for index, uri in enumerate(uris, start=1):
            suffix = ".zip" if str(uri).lower().endswith(".zip") else ".xml"
            if policy == "temporary" and not self.offline:
                snapshot = self._acquire_temporary_uri_snapshot(
                    uri,
                    suffix=suffix,
                    note="retrieval_mode=explicit_uri",
                )
            else:
                snapshot = self.acquire_uri_snapshot(
                    uri,
                    suffix=suffix,
                    note="retrieval_mode=explicit_uri; snapshot_policy=cache",
                    metadata={"snapshot_policy": "cache", "snapshot_retained": True},
                )
            snapshots.append(snapshot)
            if index == 1 or index % interval == 0 or index == total:
                self._progress(f"Acquired {index}/{total} LOC FDD URI(s)")
        return snapshots

    def acquire(self) -> list[SourceSnapshot]:
        retrieval_mode = self.config.get("retrieval_mode")
        if retrieval_mode in {"fdd_xml_zip", "zip"} or self.config.get("zip_uri"):
            return self._acquire_zip_snapshot()

        uris = list(self.config.get("uris", []))
        directory = self.config.get("directory")
        if directory:
            directory_uris = sorted(str(p) for p in Path(directory).glob("*.xml"))
            self._progress(f"Resolved {len(directory_uris)} LOC FDD XML file(s) from local directory: {directory}")
            uris.extend(directory_uris)
        return self._acquire_xml_uris(uris)

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        interval = self._progress_interval()
        for snap in snapshots:
            try:
                payloads = _xml_payloads(snap)
                total = len(payloads)
                if _snapshot_is_zip(snap):
                    self._progress(f"Extracting {total} LOC FDD XML record(s) from ZIP snapshot")
                else:
                    self._progress(f"Extracting {total} LOC FDD XML record(s) from source snapshot")
                for index, (source_file, data) in enumerate(payloads, start=1):
                    record = _record_from_xml(snap, source_file, data)
                    if record:
                        records.append(record)
                    if index == 1 or index % interval == 0 or index == total:
                        self._progress(f"Extracted {index}/{total} LOC FDD XML record(s)")
            finally:
                self._delete_temporary_snapshot(snap)
        return records
