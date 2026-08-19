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
    q123 = "http://www.wikidata.org/entity/Q123"
    q124 = "http://www.wikidata.org/entity/Q124"
    if "?format ?qid ?formatLabel ?formatDescription" in query:
        return (
            "format,qid,formatLabel,formatDescription\n"
            f"{q123},Q123,Example format,Example description\n"
            f"{q124},Q124,Format without PUID,Still a file-format item\n"
        ).encode("utf-8")
    if "skos:altLabel" in query:
        return (
            "format,alias\n"
            f"{q123},EXFMT\n"
            f"{q123},Example File Format\n"
        ).encode("utf-8")
    if "VALUES ?predicate { wdt:P31 wdt:P279 }" in query:
        return (
            "format,predicate,value,valueLabel\n"
            f"{q123},http://www.wikidata.org/prop/direct/P31,"
            "http://www.wikidata.org/entity/Q235557,file format\n"
        ).encode("utf-8")
    if "wdt:P2748 wdt:P3266 wdt:P11167" in query:
        return (
            "format,predicate,value\n"
            f"{q123},http://www.wikidata.org/prop/direct/P2748,fmt/40\n"
            f"{q123},http://www.wikidata.org/prop/direct/P3266,fdd000123\n"
            f"{q123},http://www.wikidata.org/prop/direct/P11167,NF00303\n"
            f"{q124},http://www.wikidata.org/prop/direct/P3266,fdd000999\n"
        ).encode("utf-8")
    if "wdt:P4152" in query:
        return (
            "format,predicate,value\n"
            f"{q123},http://www.wikidata.org/prop/direct/P1195,ex\n"
            f"{q123},http://www.wikidata.org/prop/direct/P1195,example\n"
            f"{q123},http://www.wikidata.org/prop/direct/P1163,application/example\n"
            f"{q123},http://www.wikidata.org/prop/direct/P348,1.0\n"
            f"{q123},http://www.wikidata.org/prop/direct/P4152,45 58\n"
            f"{q123},http://www.wikidata.org/prop/direct/P577,1997-01-01T00:00:00Z\n"
            f"{q123},http://www.wikidata.org/prop/direct/P571,1996-01-01T00:00:00Z\n"
            f"{q123},http://www.wikidata.org/prop/direct/P856,https://example.org/\n"
        ).encode("utf-8")
    if "wdt:P1343" in query:
        return (
            "format,predicate,value,valueLabel\n"
            f"{q123},http://www.wikidata.org/prop/direct/P178,"
            "http://www.wikidata.org/entity/Q456,Example Developer\n"
            f"{q123},http://www.wikidata.org/prop/direct/P361,"
            "http://www.wikidata.org/entity/Q789,Example family\n"
        ).encode("utf-8")
    raise AssertionError(f"Unexpected query: {query}")


def test_default_queries_use_file_format_properties_not_software_properties():
    query_text = "\n".join(DEFAULT_QUERY_PARTS.values())
    assert "wd:Q235557" in query_text
    assert "wdt:P2748" in query_text
    assert "wdt:P3266" in query_text
    assert "wdt:P11167" in query_text
    assert "wdt:P1195" in query_text
    assert "wdt:P1163" in query_text
    assert "wdt:P4152" in query_text
    assert "wdt:P178" in query_text
    assert "wdt:P2749" not in query_text
    assert "wdt:P3267" not in query_text


def test_wikidata_adapter_merges_file_format_metadata_without_ingestion(
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
    assert "Q124" in text
    assert "fmt/40" in text
    assert "x-sfw/" not in text
    assert "fdd000123" in text
    assert "NF00303" in text
    assert "ex|example" in text
    assert "application/example" in text
    assert "45 58" in text
    assert "Q456" in text
    assert "Example Developer" in text
    assert "Q789" in text
    assert "Example family" in text
    assert "EXFMT|Example File Format" in text

    assert len(captured_queries) == len(DEFAULT_QUERY_PARTS)
    assert snapshot.metadata["row_count"] == 2
    assert snapshot.metadata["query_mode"] == "partitioned_default_v2"
    assert set(snapshot.metadata["query_parts"]) == set(DEFAULT_QUERY_PARTS)
    assert snapshot.metadata["acquisition_only"] is True
    assert snapshot.metadata["normalization_enabled"] is False
    assert Path(snapshot.local_path).exists()
    assert adapter.extract([snapshot]) == []


def test_wikidata_adapter_reuses_cached_snapshot_offline(tmp_path, monkeypatch):
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


def test_custom_query_only_requires_format_and_qid(tmp_path, monkeypatch):
    custom_query = """
SELECT ?format ?qid WHERE {
  ?format wdt:P31 wd:Q235557 .
  BIND("Q123" AS ?qid)
}
""".strip()
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _FakeResponse(
            (
                "format,qid\n"
                "http://www.wikidata.org/entity/Q123,Q123\n"
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
