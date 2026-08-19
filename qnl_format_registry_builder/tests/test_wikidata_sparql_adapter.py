from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from registry_builder.adapters.wikidata_sparql import (
    DEFAULT_FILE_FORMAT_QUERY,
    WikidataSparqlAdapter,
)


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data
        self.headers = {"Content-Type": "text/csv; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._data


def _sample_csv() -> bytes:
    return (
        "format,qid,puid,formatLabel,locFdd,extension,mimeType,developerQid,developerLabel,publicationDate,inceptionDate\n"
        "http://www.wikidata.org/entity/Q123,Q123,fmt/40,Example format,fdd000123,ex,application/example,Q456,Example Developer,,1997-01-01T00:00:00Z\n"
    ).encode("utf-8")


def test_default_query_contains_requested_cross_registry_properties():
    assert "wdt:P2749" in DEFAULT_FILE_FORMAT_QUERY
    assert "wdt:P3267" in DEFAULT_FILE_FORMAT_QUERY
    assert "wdt:P1195" in DEFAULT_FILE_FORMAT_QUERY
    assert "wdt:P1163" in DEFAULT_FILE_FORMAT_QUERY
    assert "wdt:P178" in DEFAULT_FILE_FORMAT_QUERY
    assert "wdt:P577" in DEFAULT_FILE_FORMAT_QUERY


def test_wikidata_adapter_downloads_csv_but_extracts_no_registry_records(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(_sample_csv())

    monkeypatch.setattr("registry_builder.adapters.wikidata_sparql.urlopen", fake_urlopen)

    adapter = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "user_agent": "TestAgent/1.0 (test@example.org)",
        },
        tmp_path / "work",
    )
    output = tmp_path / "wikidata-file-formats.csv"
    snapshot = adapter.download_to(output)

    assert output.read_bytes() == _sample_csv()
    assert Path(snapshot.local_path).exists()
    assert snapshot.metadata["row_count"] == 1
    assert snapshot.metadata["acquisition_only"] is True
    assert snapshot.metadata["normalization_enabled"] is False
    assert adapter.extract([snapshot]) == []

    request = captured["request"]
    assert request.full_url == "https://query.wikidata.org/sparql"
    assert request.get_method() == "POST"
    assert request.headers["Accept"] == "text/csv"
    assert "TestAgent/1.0" in request.headers["User-agent"]
    params = parse_qs(request.data.decode("utf-8"))
    assert params["query"][0] == DEFAULT_FILE_FORMAT_QUERY


def test_wikidata_adapter_reuses_cached_snapshot_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen",
        lambda request, timeout: _FakeResponse(_sample_csv()),
    )
    workdir = tmp_path / "work"
    online = WikidataSparqlAdapter(
        {"id": "wikidata_file_formats", "type": "wikidata_sparql"},
        workdir,
    )
    online.download_to(tmp_path / "online.csv")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("offline mode must not contact Wikidata")

    monkeypatch.setattr("registry_builder.adapters.wikidata_sparql.urlopen", fail_if_called)
    offline = WikidataSparqlAdapter(
        {"id": "wikidata_file_formats", "type": "wikidata_sparql", "offline": True},
        workdir,
    )
    snapshot = offline.download_to(tmp_path / "offline.csv")

    assert snapshot.from_cache is True
    assert (tmp_path / "offline.csv").read_bytes() == _sample_csv()
