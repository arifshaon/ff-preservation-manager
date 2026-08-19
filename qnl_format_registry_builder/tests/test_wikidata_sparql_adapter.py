from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from registry_builder.adapters.wikidata_sparql import (
    DEFAULT_QUERY_PARTS,
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


def _response_for_query(query: str) -> bytes:
    if "?format ?qid ?puid ?formatLabel" in query:
        return (
            "format,qid,puid,formatLabel\n"
            "http://www.wikidata.org/entity/Q123,Q123,fmt/40,Example format\n"
        ).encode("utf-8")
    if "wdt:P3267" in query:
        return (
            "format,puid,locFdd\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,fdd000123\n"
        ).encode("utf-8")
    if "wdt:P1195" in query:
        return (
            "format,puid,extension\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,ex\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,example\n"
        ).encode("utf-8")
    if "wdt:P1163" in query:
        return (
            "format,puid,mimeType\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,application/example\n"
        ).encode("utf-8")
    if "wdt:P178" in query:
        return (
            "format,puid,developerQid,developerLabel\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,Q456,Example Developer\n"
        ).encode("utf-8")
    if "wdt:P577" in query:
        return (
            "format,puid,publicationDate\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,1997-01-01T00:00:00Z\n"
        ).encode("utf-8")
    if "wdt:P571" in query:
        return (
            "format,puid,inceptionDate\n"
            "http://www.wikidata.org/entity/Q123,fmt/40,1996-01-01T00:00:00Z\n"
        ).encode("utf-8")
    raise AssertionError(f"Unexpected query: {query}")


def test_default_queries_cover_requested_cross_registry_properties():
    query_text = "\n".join(DEFAULT_QUERY_PARTS.values())
    assert "wdt:P2749" in query_text
    assert "wdt:P3267" in query_text
    assert "wdt:P1195" in query_text
    assert "wdt:P1163" in query_text
    assert "wdt:P178" in query_text
    assert "wdt:P577" in query_text
    assert "wdt:P571" in query_text


def test_wikidata_adapter_partitions_queries_and_merges_one_csv_without_ingestion(
    tmp_path, monkeypatch
):
    captured_queries = []

    def fake_urlopen(request, timeout):
        params = parse_qs(request.data.decode("utf-8"))
        query = params["query"][0]
        captured_queries.append(query)
        return _FakeResponse(_response_for_query(query))

    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen", fake_urlopen
    )

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

    text = output.read_text(encoding="utf-8")
    assert "Q123" in text
    assert "fmt/40" in text
    assert "fdd000123" in text
    assert "ex|example" in text
    assert "application/example" in text
    assert "Q456" in text
    assert "Example Developer" in text
    assert "1997-01-01T00:00:00Z" in text
    assert "1996-01-01T00:00:00Z" in text

    assert len(captured_queries) == len(DEFAULT_QUERY_PARTS)
    assert snapshot.metadata["row_count"] == 1
    assert snapshot.metadata["query_mode"] == "partitioned_default"
    assert set(snapshot.metadata["query_parts"]) == set(DEFAULT_QUERY_PARTS)
    assert snapshot.metadata["acquisition_only"] is True
    assert snapshot.metadata["normalization_enabled"] is False
    assert Path(snapshot.local_path).exists()
    assert adapter.extract([snapshot]) == []


def test_wikidata_adapter_reuses_cached_partitioned_snapshot_offline(
    tmp_path, monkeypatch
):
    def fake_urlopen(request, timeout):
        params = parse_qs(request.data.decode("utf-8"))
        return _FakeResponse(_response_for_query(params["query"][0]))

    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen", fake_urlopen
    )
    workdir = tmp_path / "work"
    online = WikidataSparqlAdapter(
        {"id": "wikidata_file_formats", "type": "wikidata_sparql"},
        workdir,
    )
    online.download_to(tmp_path / "online.csv")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("offline mode must not contact Wikidata")

    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen", fail_if_called
    )
    offline = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "offline": True,
        },
        workdir,
    )
    snapshot = offline.download_to(tmp_path / "offline.csv")

    assert snapshot.from_cache is True
    assert (tmp_path / "offline.csv").read_bytes() == (
        tmp_path / "online.csv"
    ).read_bytes()


def test_custom_query_still_uses_single_request(tmp_path, monkeypatch):
    custom_query = """
SELECT ?format ?qid ?puid WHERE {
  ?format wdt:P2749 ?puid .
  BIND("Q123" AS ?qid)
}
""".strip()
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _FakeResponse(
            (
                "format,qid,puid\n"
                "http://www.wikidata.org/entity/Q123,Q123,fmt/40\n"
            ).encode("utf-8")
        )

    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen", fake_urlopen
    )
    adapter = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "query": custom_query,
        },
        tmp_path / "work",
    )
    snapshot = adapter.download_to(tmp_path / "custom.csv")

    assert len(calls) == 1
    params = parse_qs(calls[0].data.decode("utf-8"))
    assert params["query"][0] == custom_query
    assert snapshot.metadata["query_mode"] == "custom_single_query"
