from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


class PronomDroidXmlAdapter(SourceAdapter):
    """Parse PRONOM/DROID signature XML files.

    This adapter is intended for the DROID signature XML generated from PRONOM.
    It extracts identity metadata, not preservation hazard.
    """

    type_name = "pronom_droid_xml"

    inbox_hint = (
        "Drop DROID signature file XML(s) here (e.g. "
        "DROID_SignatureFile_V120.xml). The signature version in the filename "
        "is the edition; record its release date in manifest.json if you want "
        "data age reported."
    )

    def network_acquire(self) -> list[SourceSnapshot]:
        return [self.acquire_uri_snapshot(uri, suffix=".xml") for uri in self.config.get("uris", [])]

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snap in snapshots:
            root = ET.parse(snap.local_path).getroot()
            for elem in root.iter():
                if _local_name(elem.tag) != "FileFormat":
                    continue
                name = elem.attrib.get("Name") or elem.attrib.get("name")
                version = elem.attrib.get("Version") or elem.attrib.get("version")
                puid = elem.attrib.get("PUID") or elem.attrib.get("Puid")
                mime = elem.attrib.get("MIMEType") or elem.attrib.get("MIME")
                extensions: list[str] = []
                for child in list(elem):
                    if _local_name(child.tag) in {"Extension", "FileExtension"} and child.text:
                        extensions.append(child.text.strip())
                display_name = f"{name} {version}".strip() if version else name
                records.append(RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id=puid,
                    name=display_name,
                    extensions=extensions,
                    mime_types=[mime] if mime else [],
                    puids=[puid] if puid else [],
                    urls={"pronom": f"https://www.nationalarchives.gov.uk/PRONOM/{puid}"} if puid else {},
                    raw={"attrib": dict(elem.attrib), "snapshot_sha256": snap.sha256},
                ))
        return records
