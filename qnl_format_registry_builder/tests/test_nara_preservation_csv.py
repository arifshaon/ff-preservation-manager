import json

from registry_builder.adapters.nara_digital_preservation_framework import NaraDigitalPreservationFrameworkAdapter
from registry_builder.adapters.nara_preservation_csv import NaraPreservationCsvAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


def test_nara_source_adapter_extracts_native_and_normalized_hazard(tmp_path):
    csv_path = tmp_path / "nara.csv"
    csv_path.write_text(
        "Format Name,File Extension(s),Category/Plan(s),NARA Format ID,MIME type(s),PRONOM URL,LOC URL,WikiData URL,NARA Risk Level,NARA Preservation Action,NARA Proposed Preservation Plan,Description and Justification,NARA Preferred Processing and Transformation Tool(s),Numeric Risk Rating,NARA TOTAL\n"
        "Comma Separated Values,csv,Structured Data,NF00143,text/csv,https://www.nationalarchives.gov.uk/PRONOM/fmt/18,https://www.loc.gov/preservation/digital/formats/fdd/fdd000323.shtml,https://www.wikidata.org/wiki/Q935809,Low Risk,Retain,Retain,Delimited structured data,CSV validator,24.00,-7.00\n",
        encoding="utf-8",
    )
    adapter = NaraDigitalPreservationFrameworkAdapter({"id": "nara_test", "uris": []}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="nara_test",
        source_type="nara_digital_preservation_framework",
        uri=str(csv_path),
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(csv_path),
        content_type="text/csv",
        metadata={"release_mode": "pinned", "release_date": "20260320", "kind": "risk_matrix_numbered"},
    )

    records = adapter.extract([snapshot])

    assert len(records) == 1
    record = records[0]
    assert record.source_type == "nara_digital_preservation_framework"
    assert record.name == "Comma Separated Values"
    assert record.nara_ids == ["NF00143"]
    assert record.extensions == ["csv"]
    assert record.hazard["external_band"] == "Low"
    assert record.hazard["rating"] == 1.0
    assert record.hazard["native_rating"] == 24.0
    assert record.hazard["external_rating_native"] == 24.0
    assert record.hazard["native_rating_band"] == "Low"
    assert record.hazard["native_direction"] == "higher_is_safer"
    assert record.hazard["external_rating_native_direction"] == "higher_is_safer"
    assert record.hazard["nara_total"] == -7.0
    assert record.evidence[0]["nara_release_date"] == "20260320"
    assert record.raw["snapshot_metadata"]["kind"] == "risk_matrix_numbered"


def test_nara_native_rating_drives_band_when_text_is_absent(tmp_path):
    csv_path = tmp_path / "nara.csv"
    csv_path.write_text(
        "Format Name,File Extension(s),NARA Format ID,Numeric Risk Rating\n"
        "Legacy Binary,bin,NF00999,-24.00\n",
        encoding="utf-8",
    )
    adapter = NaraDigitalPreservationFrameworkAdapter({"id": "nara_test", "uris": []}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="nara_test",
        source_type="nara_digital_preservation_framework",
        uri=str(csv_path),
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(csv_path),
    )

    record = adapter.extract([snapshot])[0]

    assert record.hazard["external_band"] == "High"
    assert record.hazard["rating"] == 3.0
    assert record.hazard["external_rating_native"] == -24.0
    assert record.hazard["external_rating_native_direction"] == "higher_is_safer"


def test_nara_id_is_verified_but_pronom_url_puid_is_not(tmp_path):
    csv_path = tmp_path / "nara.csv"
    csv_path.write_text(
        "Format Name,File Extension(s),Category/Plan(s),NARA Format ID,PRONOM URL,Risk Level\n"
        "Portable Document Format,pdf,Textual and Word Processing,NF00001,https://www.nationalarchives.gov.uk/PRONOM/fmt/18,Moderate Risk\n",
        encoding="utf-8",
    )
    adapter = NaraDigitalPreservationFrameworkAdapter({"id": "nara_test", "uris": []}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="nara_test",
        source_type="nara_digital_preservation_framework",
        uri=str(csv_path),
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(csv_path),
    )

    record = normalize_record(adapter.extract([snapshot])[0])

    assert any(claim.kind == "nara" and claim.value == "NF00001" and claim.verified for claim in record.identifiers)
    assert any(claim.kind == "puid" and claim.value == "fmt/18" and not claim.verified for claim in record.identifiers)


def test_nara_pinned_release_resolves_dated_pair(tmp_path):
    adapter = NaraDigitalPreservationFrameworkAdapter(
        {"id": "nara_test", "release_mode": "pinned", "release_date": "20260320", "github_ref": "master"},
        tmp_path,
    )

    sources = adapter._resolved_sources()

    assert [source["kind"] for source in sources] == ["preservation_action_plan", "risk_matrix_numbered"]
    assert {source["release_date"] for source in sources} == {"20260320"}
    assert all("20260320" in source["uri"] for source in sources)
    assert all(source["release_mode"] == "pinned" for source in sources)


def test_nara_latest_release_resolves_highest_common_dated_pair(tmp_path, monkeypatch):
    adapter = NaraDigitalPreservationFrameworkAdapter(
        {"id": "nara_test", "release_mode": "latest", "github_ref": "master"},
        tmp_path,
    )

    def fake_directory(directory):
        if directory == "Digital_Preservation_Plan_Spreadsheet":
            return [
                {"name": "NARA_PreservationActionPlan_FileFormats_20250101.csv", "path": f"{directory}/NARA_PreservationActionPlan_FileFormats_20250101.csv", "download_url": "https://example.test/action-20250101.csv", "sha": "sha-action-old"},
                {"name": "NARA_PreservationActionPlan_FileFormats_20260320.csv", "path": f"{directory}/NARA_PreservationActionPlan_FileFormats_20260320.csv", "download_url": "https://example.test/action-20260320.csv", "sha": "sha-action-new"},
            ]
        return [
            {"name": "NARA_File_Format_Risk_Matrix_20250101_Numbered.csv", "path": f"{directory}/NARA_File_Format_Risk_Matrix_20250101_Numbered.csv", "download_url": "https://example.test/risk-20250101.csv", "sha": "sha-risk-old"},
            {"name": "NARA_File_Format_Risk_Matrix_20260320_Numbered.csv", "path": f"{directory}/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv", "download_url": "https://example.test/risk-20260320.csv", "sha": "sha-risk-new"},
        ]

    monkeypatch.setattr(adapter, "_fetch_github_directory", fake_directory)

    sources = adapter._resolved_sources()

    assert {source["release_date"] for source in sources} == {"20260320"}
    assert {source["github_blob_sha"] for source in sources} == {"sha-action-new", "sha-risk-new"}
    release_index = json.loads((tmp_path / "snapshots" / "nara_test" / ".nara_release_index.json").read_text(encoding="utf-8"))
    assert release_index["latest"]["release_date"] == "20260320"


def test_nara_latest_offline_uses_cached_release_index(tmp_path):
    release_dir = tmp_path / "snapshots" / "nara_test"
    release_dir.mkdir(parents=True)
    (release_dir / ".nara_release_index.json").write_text(
        json.dumps(
            {
                "latest": {
                    "release_date": "20260320",
                    "sources": [
                        {"uri": "https://example.test/action.csv", "kind": "preservation_action_plan", "release_date": "20260320", "github_ref": "master"},
                        {"uri": "https://example.test/risk.csv", "kind": "risk_matrix_numbered", "release_date": "20260320", "github_ref": "master"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    adapter = NaraDigitalPreservationFrameworkAdapter(
        {"id": "nara_test", "release_mode": "latest", "offline": True},
        tmp_path,
    )

    sources = adapter._resolved_sources()

    assert [source["uri"] for source in sources] == ["https://example.test/action.csv", "https://example.test/risk.csv"]
    assert all(source["release_mode"] == "latest" for source in sources)


def test_legacy_nara_csv_adapter_alias_keeps_old_type_name(tmp_path):
    adapter = NaraPreservationCsvAdapter({"id": "nara_legacy", "uris": []}, tmp_path)
    assert adapter.type_name == "nara_preservation_csv"
