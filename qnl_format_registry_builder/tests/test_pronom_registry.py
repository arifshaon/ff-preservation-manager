import json
import zipfile
from pathlib import Path

import registry_builder.adapters.base as adapter_base
import registry_builder.adapters.pronom_registry as pronom_module
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


def test_pronom_github_json_tree_uses_temporary_snapshots_by_default(monkeypatch, tmp_path):
    tree_url = "https://api.github.test/pronom/tree"
    raw_url = "https://raw.example/pronom/develop/signatures/fmt/18.json"
    tree_payload = {
        "tree": [
            {"path": "signatures/fmt/18.json", "type": "blob"},
            {"path": "signatures/fmt/readme.txt", "type": "blob"},
            {"path": "other/ignored.json", "type": "blob"},
        ]
    }

    def fake_read_uri(uri: str):
        if uri == tree_url:
            return json.dumps(tree_payload).encode("utf-8"), {"content-type": "application/json"}
        if uri == raw_url:
            return json.dumps(PRONOM_RECORD).encode("utf-8"), {"content-type": "application/json"}
        raise AssertionError(f"unexpected URI: {uri}")

    monkeypatch.setattr(adapter_base, "read_uri", fake_read_uri)
    monkeypatch.setattr(pronom_module, "read_uri", fake_read_uri)

    adapter = PronomRegistryAdapter(
        {
            "id": "pronom_registry",
            "retrieval_mode": "github_json",
            "github_tree_url": tree_url,
            "raw_base_url": "https://raw.example/pronom/develop",
            "include_paths": ["signatures/fmt/"],
            "progress": False,
        },
        tmp_path,
    )

    snapshots = adapter.acquire()

    assert len(snapshots) == 1
    assert snapshots[0].metadata["snapshot_policy"] == "temporary"
    assert snapshots[0].metadata["delete_after_extract"] is True
    assert Path(snapshots[0].local_path).exists()

    records = [normalize_record(r) for r in adapter.extract(snapshots)]

    assert len(records) == 1
    assert records[0].source_record_id == "fmt/18"
    assert records[0].raw["record"]["formatName"] == PRONOM_RECORD["formatName"]
    assert records[0].evidence[0]["snapshot_policy"] == "temporary"
    assert records[0].evidence[0]["snapshot_retained"] is False
    assert not Path(snapshots[0].local_path).exists()


def test_pronom_targeted_puid_keeps_cache_snapshots_by_default(monkeypatch, tmp_path):
    raw_url = "https://raw.githubusercontent.com/nationalarchives/pronom/develop/signatures/fmt/18.json"

    def fake_read_uri(uri: str):
        assert uri == raw_url
        return json.dumps(PRONOM_RECORD).encode("utf-8"), {"content-type": "application/json"}

    monkeypatch.setattr(adapter_base, "read_uri", fake_read_uri)

    adapter = PronomRegistryAdapter(
        {"id": "pronom_registry", "retrieval_mode": "github_json", "puids": ["fmt/18"], "progress": False},
        tmp_path,
    )

    snapshots = adapter.acquire()
    records = [normalize_record(r) for r in adapter.extract(snapshots)]

    assert len(records) == 1
    assert snapshots[0].metadata["snapshot_policy"] == "cache"
    assert snapshots[0].metadata["snapshot_retained"] is True
    assert Path(snapshots[0].local_path).exists()


def test_pronom_puid_to_raw_url_supports_fmt_and_xfmt():
    assert _puid_to_raw_url("fmt/18").endswith("/signatures/fmt/18.json")
    assert _puid_to_raw_url("x-fmt/111").endswith("/signatures/x-fmt/111.json")
