from pathlib import Path
import zipfile

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


LOC_XML = """<?xml version='1.0' encoding='UTF-8'?>
<fdd>
  <fddID>fdd000030</fddID>
  <title>PDF, Portable Document Format</title>
  <category>Text</category>
  <fileExtension>.pdf</fileExtension>
  <note>PRONOM identifier fmt/18; Wikidata Q42332; see https://www.loc.gov/0.4/path.</note>
</fdd>
"""


def _zip_snapshot(archive: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        uri="https://www.loc.gov/preservation/digital/formats/fddXML.zip",
        acquired_at="2026-08-15T00:00:00+00:00",
        sha256="abc123",
        local_path=str(archive),
        content_type="application/zip",
        metadata={"snapshot_policy": "cache", "snapshot_retained": True},
    )


def test_loc_fdd_xml_extracts_records_from_zip_snapshot(tmp_path):
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000030.xml", LOC_XML)
        zf.writestr("README.txt", "not xml")

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.source_record_id == "fdd000030"
    assert record.name == "PDF, Portable Document Format"
    assert record.category == "Text"
    assert record.loc_ids == ["fdd000030"]
    assert record.puids == ["fmt/18"]
    assert record.wikidata_ids == ["Q42332"]
    assert record.extensions == ["pdf"]
    assert record.urls["loc"] == "https://www.loc.gov/preservation/digital/formats/fddXML/fdd000030.xml"
    assert record.evidence[0]["type"] == "loc_fdd_xml_zip"
    assert record.evidence[0]["source_file"] == "fdd000030.xml"
    assert record.evidence[0]["snapshot_policy"] == "cache"
    assert record.evidence[0]["snapshot_retained"] is True
    assert "xml_text" not in record.raw


def test_loc_fdd_xml_uses_filename_not_referenced_fdd_id(tmp_path):
    archive = tmp_path / "fddXML.zip"
    webp_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <title>WebP</title>
      <category>file-format</category>
      <relatedFormat><id>fdd000025</id><name>RIFF</name></relatedFormat>
      <sustainabilityFactors>
        <disclosure>Open source, anyone can work with the WebP format.</disclosure>
        <externalDependencies>None beyond availability of supporting software/hardware.</externalDependencies>
      </sustainabilityFactors>
    </fdd>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fddXML/fdd000577.xml", webp_xml)

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.source_record_id == "fdd000577"
    assert record.loc_ids == ["fdd000577"]
    assert record.urls["loc"] == "https://www.loc.gov/preservation/digital/formats/fddXML/fdd000577.xml"
    assert record.evidence[0]["source_file"] == "fddXML/fdd000577.xml"
    assert record.native_fields["sustainability_factors"]["disclosure"].startswith("Open source")
    assert "fdd000025" not in record.loc_ids


def test_loc_fdd_xml_uses_top_level_title_not_related_format_title(tmp_path):
    archive = tmp_path / "fddXML.zip"
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <relatedFormat><title>RIFF</title><id>fdd000025</id></relatedFormat>
      <title>WAVE Audio File Format</title>
      <category>file-format</category>
      <fileExtension>wav</fileExtension>
    </fdd>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fddXML/fdd000001.xml", xml)

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.source_record_id == "fdd000001"
    assert record.name == "WAVE Audio File Format"
    assert record.category == "file-format"
    assert record.loc_ids == ["fdd000001"]


def test_loc_fdd_xml_skips_auxiliary_xml_files_in_zip(tmp_path):
    archive = tmp_path / "fddXML.zip"
    dwsync_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <dwsync>
      <file name="fdd000033.xml" />
      <url>https://www.loc.gov/preservation/digital/formats/fddXML/fdd000033.xml</url>
      <note>Mentions .0, .gov, .loc, .txt and .xml but is not an FDD record.</note>
    </dwsync>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fddXML/fdd000030.xml", LOC_XML)
        zf.writestr("fddXML/_notes/dwsync.xml", dwsync_xml)

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    records = [normalize_record(record) for record in adapter.extract([snapshot])]

    assert len(records) == 1
    assert records[0].source_record_id == "fdd000030"
    assert records[0].evidence[0]["source_file"] == "fddXML/fdd000030.xml"
    assert "0" not in records[0].extensions
    assert "gov" not in records[0].extensions
    assert "loc" not in records[0].extensions


def test_loc_fdd_xml_does_not_extract_extensions_from_free_text(tmp_path):
    archive = tmp_path / "fddXML.zip"
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <fddID>fdd000031</fddID>
      <title>Format with URL and decimal references</title>
      <category>Text</category>
      <fileExtension>pdf; xml; .jp2</fileExtension>
      <note>Do not extract junk from https://www.loc.gov, version 1.0, or PDF 1.4 text.</note>
    </fdd>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000031.xml", xml)

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.extensions == ["jp2", "pdf", "xml"]
    assert "0" not in record.extensions
    assert "4" not in record.extensions
    assert "gov" not in record.extensions
    assert "loc" not in record.extensions


def test_loc_fdd_xml_never_uses_dot_regex_over_free_text(tmp_path):
    archive = tmp_path / "fddXML.zip"
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <fddID>fdd000032</fddID>
      <title>Format with dotted free text only</title>
      <category>Text</category>
      <note>Free text mentions .0, .gov, .loc, .jpg, and https://www.loc.gov/path.</note>
    </fdd>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000032.xml", xml)

    snapshot = _zip_snapshot(archive)

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.extensions == []


def test_loc_fdd_xml_acquires_local_zip_uri(tmp_path):
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000001.xml", "<fdd><fddID>fdd000001</fddID><title>WAVE Audio File Format</title></fdd>")

    adapter = LocFddXmlAdapter(
        {"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "zip_uri": str(archive), "progress": False},
        tmp_path,
    )

    snapshots = adapter.acquire()

    assert len(snapshots) == 1
    assert snapshots[0].local_path.endswith(".zip")
    assert snapshots[0].metadata["source_location"] == "loc_fdd_xml_zip"
    assert snapshots[0].metadata["snapshot_policy"] == "cache"
    assert snapshots[0].metadata["snapshot_retained"] is True


def test_loc_fdd_xml_temporary_uri_snapshot_is_deleted_after_extract(tmp_path):
    xml_path = tmp_path / "fdd000030.xml"
    xml_path.write_text(LOC_XML, encoding="utf-8")
    adapter = LocFddXmlAdapter(
        {
            "id": "loc_fdd_xml",
            "uris": [str(xml_path)],
            "snapshot_policy": "temporary",
            "progress": False,
        },
        tmp_path,
    )

    snapshots = adapter.acquire()

    assert len(snapshots) == 1
    assert snapshots[0].metadata["snapshot_policy"] == "temporary"
    assert snapshots[0].metadata["snapshot_retained"] is False
    assert snapshots[0].metadata["delete_after_extract"] is True
    assert snapshots[0].local_path != str(xml_path)
    assert xml_path.exists()
    assert Path(snapshots[0].local_path).exists()

    records = [normalize_record(r) for r in adapter.extract(snapshots)]

    assert len(records) == 1
    assert records[0].loc_ids == ["fdd000030"]
    assert records[0].evidence[0]["snapshot_policy"] == "temporary"
    assert records[0].evidence[0]["snapshot_retained"] is False
    assert "xml_text" in records[0].raw
    assert xml_path.exists()
    assert not Path(snapshots[0].local_path).exists()
