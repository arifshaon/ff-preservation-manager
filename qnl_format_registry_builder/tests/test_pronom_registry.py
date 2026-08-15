import json
import zipfile

from registry_builder.adapters.pronom_registry import PronomRegistryAdapter, _puid_to_raw_url
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


PRONOM_RECORD = {
    "fileFormatID": 617,
    "formatName": "Acrobat PDF 1.4 - Portable Document Format",
    "version": "1.4",
    "formatDescription": "Portable Document Format description.",
    "formatTypes": "Page Description",
    "formatDisclosure": "Full",
    "lastUpdatedDate": "22 Oct 2009",
    "formatRisk": None,
    "identifiers": [
        {"identifierText": "application/pdf", "identifierType": "MIME"},
        {"identifierText": "fmt/18", "identifierType": "PUID"},
    ],
    "externalSignatures": [
        {"externalSignature": "pdf", "signatureType": "File extension"}
    ],
}


def test_pronom_registry_extracts_github_json_record(tmp_path):
    record_path = tmp_path / "18.json"
    record_path.write_text(json.dumps(PRONOM_RECORD), encoding="utf-8")
    adapter = PronomRegistryAdapter({"id": "pronom_test", "puids": [], "progress": False}, tmp_path)
    snapshot = SourceSnapshot(
        source_id="pronom_test",
        source_type="pronom_registry",
        uri="https://raw.githubusercontent.com/nationalarchives/pronom/develop/signatures/fmt/18.json",
        acquired_at="2026-08-14T00:00:00+00:00",
        sha256="abc123",
        local_path=str(record_path),
        content_type="application/json",
    )

    record = normalize_record(adapter.extract([snapshot])[0])

    assert record.name == "Acrobat PDF 1.4 - Portable Document Format"
    assert record.category == "Page Description"
    assert record.description == "Portable Document Format description."
    assert record.extensions == ["pdf"]
    assert record.mime_types == ["application/pdf"]
    assert record.puids == ["fmt/18"]
    assert record.urls["pronom"] == "https://pronom.nationalarchives.gov.uk/fmt/18"
    assert any(claim.kind == "puid" and claim.value == "fmt/18" and claim.verified for claim in record.identifiers)


def test_pronom_registry_extracts_records_from_one_archive_snapshot(tmp_path):
    archive_path = tmp_path / "pronom-develop.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("pronom-develop/signatures/fmt/18.json", json.dumps(PRONOM_RECORD))
        zf.writestr("pronom-develop/signatures/fmt/readme.txt", "not json")
        zf.writestr("pronom-develop/other/ignored.json", json.dumps(PRONOM_RECORD))

    adapter = PronomRegistryAdapter(
        {
            "id": "pronom_registry",
            "retrieval_mode": "github_archive",
            "include_paths": ["signatures/fmt/", "signatures/x-fmt/"],
            "progress": False,
        },
        tmp_path,
    )
    snapshot = SourceSnapshot(
        source_id="pronom_registry",
        source_type="pronom_registry",
        uri="https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip",
        acquired_at="2026-08-15T00:00:00+00:00",
        sha256="zip123",
        local_path=str(archive_path),
        content_type="application/zip",
    )

    records = [normalize_record(r) for r in adapter.extract([snapshot])]

    assert len(records) == 1
    record = records[0]
    assert record.source_record_id == "fmt/18"
    assert record.puids == ["fmt/18"]
    assert record.evidence[0]["type"] == "pronom_registry_github_archive"
    assert record.evidence[0]["source_archive"] == snapshot.uri
    assert record.evidence[0]["source_file"] == "pronom-develop/signatures/fmt/18.json"


def test_pronom_puid_to_raw_url_supports_fmt_and_xfmt():
    assert _puid_to_raw_url("fmt/18").endswith("/signatures/fmt/18.json")
    assert _puid_to_raw_url("x-fmt/111").endswith("/signatures/x-fmt/111.json")
