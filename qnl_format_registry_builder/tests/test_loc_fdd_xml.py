import zipfile

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


def test_loc_fdd_xml_extracts_records_from_zip_snapshot(tmp_path):
    archive = tmp_path / "fddXML.zip"
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <fdd>
      <fddID>fdd000030</fddID>
      <title>PDF, Portable Document Format</title>
      <category>Text</category>
      <note>PRONOM identifier fmt/18; Wikidata Q42332; file extension .pdf.</note>
    </fdd>
    """
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000030.xml", xml)
        zf.writestr("README.txt", "not xml")

    snapshot = SourceSnapshot(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        uri="https://www.loc.gov/preservation/digital/formats/fddXML.zip",
        acquired_at="2026-08-15T00:00:00+00:00",
        sha256="abc123",
        local_path=str(archive),
        content_type="application/zip",
    )

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip"}, tmp_path)
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


def test_loc_fdd_xml_acquires_local_zip_uri(tmp_path):
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000001.xml", "<fdd><fddID>fdd000001</fddID><title>WAVE Audio File Format</title></fdd>")

    adapter = LocFddXmlAdapter(
        {"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "zip_uri": str(archive)},
        tmp_path,
    )

    snapshots = adapter.acquire()

    assert len(snapshots) == 1
    assert snapshots[0].local_path.endswith(".zip")
    assert snapshots[0].metadata["source_location"] == "loc_fdd_xml_zip"
