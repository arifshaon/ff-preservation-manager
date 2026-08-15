from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot

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
        }],
        raw={"snapshot_sha256": snapshot.sha256, "source_file": source_file},
    )


class LocFddXmlAdapter(SourceAdapter):
    """Acquire and parse Library of Congress FDD XML records.

    LOC's FDD XML is used here as sustainability evidence and identifiers. The
    adapter supports the official FDD XML ZIP as the default online acquisition
    mode, plus explicit XML URIs and local XML directories for admin-staged runs.
    """

    type_name = "loc_fdd_xml"

    def acquire(self) -> list[SourceSnapshot]:
        retrieval_mode = self.config.get("retrieval_mode")
        if retrieval_mode in {"fdd_xml_zip", "zip"} or self.config.get("zip_uri"):
            uri = self.config.get("zip_uri") or self.config.get("uri") or DEFAULT_LOC_FDD_XML_ZIP
            return [self.acquire_uri_snapshot(
                uri,
                suffix=".zip",
                note="retrieval_mode=fdd_xml_zip",
                metadata={"source_location": "loc_fdd_xml_zip"},
            )]

        uris = list(self.config.get("uris", []))
        directory = self.config.get("directory")
        if directory:
            uris.extend(str(p) for p in Path(directory).glob("*.xml"))
        snapshots: list[SourceSnapshot] = []
        for uri in uris:
            suffix = ".zip" if str(uri).lower().endswith(".zip") else ".xml"
            snapshots.append(self.acquire_uri_snapshot(uri, suffix=suffix))
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snap in snapshots:
            for source_file, data in _xml_payloads(snap):
                record = _record_from_xml(snap, source_file, data)
                if record:
                    records.append(record)
        return records
