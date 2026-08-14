from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _text_by_names(root: ET.Element, names: set[str]) -> list[str]:
    out: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) in names and elem.text and elem.text.strip():
            out.append(elem.text.strip())
    return out


class LocFddXmlAdapter(SourceAdapter):
    """Parse Library of Congress FDD XML records.

    LOC's FDD XML is used here as sustainability evidence and identifiers. This
    adapter extracts a conservative subset and leaves detailed claim extraction
    to later evidence-claim modules.
    """

    type_name = "loc_fdd_xml"

    def acquire(self) -> list[SourceSnapshot]:
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        snapshots: list[SourceSnapshot] = []
        uris = list(self.config.get("uris", []))
        directory = self.config.get("directory")
        if directory:
            uris.extend(str(p) for p in Path(directory).glob("*.xml"))
        for uri in uris:
            data, headers = read_uri(uri)
            digest = sha256_bytes(data)
            local_path = snapshot_dir / f"{digest}.xml"
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
        records: list[RawFormatRecord] = []
        for snap in snapshots:
            text = Path(snap.local_path).read_text(encoding="utf-8", errors="replace")
            root = ET.fromstring(text)
            loc_ids = _text_by_names(root, {"fddid", "fdd_id", "id"})
            titles = _text_by_names(root, {"title", "shortname", "short_name"})
            categories = _text_by_names(root, {"category", "type"})
            # Conservative regex fallbacks for common identifiers.
            puids = sorted(set(re.findall(r"\b(?:fmt|x-fmt)/\d+\b", text)))
            wikidata = sorted(set(re.findall(r"\bQ\d{2,}\b", text)))
            extensions = sorted(set(x.lower() for x in re.findall(r"\.([A-Za-z0-9]{1,12})\b", text)))
            name = titles[0] if titles else None
            loc_id = next((x for x in loc_ids if re.match(r"fdd\d+", x, re.I)), None)
            records.append(RawFormatRecord(
                source_id=self.source_id,
                source_type=self.type_name,
                source_record_id=loc_id or snap.uri,
                name=name,
                category=categories[0] if categories else None,
                extensions=extensions,
                puids=puids,
                loc_ids=[loc_id] if loc_id else [],
                wikidata_ids=wikidata,
                urls={"loc": snap.uri},
                evidence=[{"type": "loc_fdd_xml_text", "snapshot_sha256": snap.sha256}],
                raw={"snapshot_sha256": snap.sha256},
            ))
        return records
