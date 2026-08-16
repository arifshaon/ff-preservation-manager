import zipfile

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import SourceSnapshot


LOC_XML_WITH_SUSTAINABILITY = """<?xml version='1.0' encoding='UTF-8'?>
<fdd>
  <fddID>fdd000999</fddID>
  <title>Test Format</title>
  <category>Text</category>
  <fileExtension>.tst</fileExtension>
  <sustainabilityFactors>
    <disclosure>Fully disclosed. A published specification is available.</disclosure>
    <adoption>Widely used in cultural heritage workflows.</adoption>
    <transparency>Plain text and human-readable.</transparency>
    <selfDocumentation>Includes embedded metadata.</selfDocumentation>
    <externalDependencies>None.</externalDependencies>
    <impactOfPatents>No known patent claims.</impactOfPatents>
    <technicalProtectionConsiderations>None.</technicalProtectionConsiderations>
  </sustainabilityFactors>
</fdd>
"""


def test_loc_fdd_xml_extracts_sustainability_factors_as_native_fields(tmp_path):
    archive = tmp_path / "fddXML.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fdd000999.xml", LOC_XML_WITH_SUSTAINABILITY)

    snapshot = SourceSnapshot(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        uri="https://www.loc.gov/preservation/digital/formats/fddXML.zip",
        acquired_at="2026-08-16T00:00:00+00:00",
        sha256="abc123",
        local_path=str(archive),
        content_type="application/zip",
        metadata={"snapshot_policy": "cache", "snapshot_retained": True},
    )

    adapter = LocFddXmlAdapter({"id": "loc_fdd_xml", "retrieval_mode": "fdd_xml_zip", "progress": False}, tmp_path)
    record = adapter.extract([snapshot])[0]

    factors = record.native_fields["sustainability_factors"]
    assert factors["disclosure"].startswith("Fully disclosed")
    assert factors["adoption"].startswith("Widely used")
    assert factors["transparency"].startswith("Plain text")
    assert factors["self_documentation"].startswith("Includes embedded metadata")
    assert factors["external_dependencies"] == "None."
    assert factors["impact_of_patents"].startswith("No known patent")
    assert factors["technical_protection_mechanisms"] == "None."
    assert record.evidence[0]["sustainability_factor_count"] == 7
