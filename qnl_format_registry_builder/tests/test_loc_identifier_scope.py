from pathlib import Path
import zipfile

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


def _snapshot(path: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        uri="https://www.loc.gov/preservation/digital/formats/fddXML.zip",
        acquired_at="2026-08-18T00:00:00+00:00",
        sha256="test",
        local_path=str(path),
        content_type="application/zip",
        metadata={"snapshot_policy": "cache", "snapshot_retained": True},
    )


def test_loc_puids_ignore_related_and_reference_subtrees(tmp_path):
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <fddID>fdd000316</fddID>
      <title>PDF Versions 1.0-1.3</title>
      <note>Current record PRONOM identifiers fmt/14 and fmt/15.</note>
      <relatedFormat>
        <name>Different related format</name>
        <note>Related-format identifier fmt/9999 must not belong to this record.</note>
      </relatedFormat>
      <references>
        <reference>Reference text mentions x-fmt/777 and Q999999.</reference>
      </references>
      <note>Current record Wikidata Q12345.</note>
    </fdd>
    """
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000316.xml", xml)

    adapter = LocFddXmlAdapter(
        {"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False},
        tmp_path,
    )
    record = normalize_record(adapter.extract([_snapshot(archive)])[0])

    assert record.puids == ["fmt/14", "fmt/15"]
    assert record.wikidata_ids == ["Q12345"]
    assert "fmt/9999" not in record.puids
    assert "x-fmt/777" not in record.puids
    assert "Q999999" not in record.wikidata_ids


def test_loc_puid_only_in_related_format_does_not_become_current_record_identifier(tmp_path):
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <fddID>fdd000900</fddID>
      <title>Generic family record</title>
      <relatedFormat><note>PRONOM fmt/18</note></relatedFormat>
    </fdd>
    """
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000900.xml", xml)

    adapter = LocFddXmlAdapter(
        {"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False},
        tmp_path,
    )
    record = normalize_record(adapter.extract([_snapshot(archive)])[0])

    assert record.puids == []
