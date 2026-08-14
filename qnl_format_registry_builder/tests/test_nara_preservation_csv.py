from registry_builder.adapters.nara_preservation_csv import NaraPreservationCsvAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


def test_nara_csv_extracts_native_and_normalized_hazard(tmp_path):
    csv_path = tmp_path / "nara.csv"
    csv_path.write_text(
        "Format Name,File Extension(s),Category/Plan(s),NARA Format ID,MIME type(s),PRONOM URL,LOC URL,WikiData URL,NARA Risk Level,NARA Preservation Action,NARA Proposed Preservation Plan,Description and Justification,NARA Preferred Processing and Transformation Tool(s),Numeric Risk Rating,NARA TOTAL\n"
        "Comma Separated Values,csv,Structured Data,NF00143,text/csv,https://www.nationalarchives.gov.uk/PRONOM/fmt/18,https://www.loc.gov/preservation/digital/formats/fdd/fdd000323.shtml,https://www.wikidata.org/wiki/Q935809,Low Risk,Retain,Retain,Delimited structured data,CSV validator,-12.00,-7.00\n",
        encoding="utf-8",
    )
    adapter = NaraPreservationCsvAdapter({"id": "nara_test", "uris": []}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="nara_test",
        source_type="nara_preservation_csv",
        uri=str(csv_path),
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(csv_path),
        content_type="text/csv",
    )

    records = adapter.extract([snapshot])

    assert len(records) == 1
    record = records[0]
    assert record.name == "Comma Separated Values"
    assert record.nara_ids == ["NF00143"]
    assert record.extensions == ["csv"]
    assert record.hazard["external_band"] == "Low"
    assert record.hazard["rating"] == 1.0
    assert record.hazard["native_rating"] == -12.0
    assert record.hazard["native_direction"] == "higher_is_safer"
    assert record.hazard["nara_total"] == -7.0


def test_nara_id_is_verified_but_pronom_url_puid_is_not(tmp_path):
    csv_path = tmp_path / "nara.csv"
    csv_path.write_text(
        "Format Name,File Extension(s),Category/Plan(s),NARA Format ID,PRONOM URL,Risk Level\n"
        "Portable Document Format,pdf,Textual and Word Processing,NF00001,https://www.nationalarchives.gov.uk/PRONOM/fmt/18,Moderate Risk\n",
        encoding="utf-8",
    )
    adapter = NaraPreservationCsvAdapter({"id": "nara_test", "uris": []}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="nara_test",
        source_type="nara_preservation_csv",
        uri=str(csv_path),
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(csv_path),
    )

    record = normalize_record(adapter.extract([snapshot])[0])

    assert any(claim.kind == "nara" and claim.value == "NF00001" and claim.verified for claim in record.identifiers)
    assert any(claim.kind == "puid" and claim.value == "fmt/18" and not claim.verified for claim in record.identifiers)
