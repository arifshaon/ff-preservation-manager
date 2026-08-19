from __future__ import annotations

from http.client import IncompleteRead

from registry_builder.adapters.wikidata_sparql import WikidataSparqlAdapter
from registry_builder.wikidata_download import _TransportRetryingWikidataSparqlAdapter


def test_transport_retry_repeats_only_failed_query_part(tmp_path, monkeypatch):
    calls = {"count": 0}

    def flaky_request(self, query, *, query_name, required_columns):
        calls["count"] += 1
        if calls["count"] == 1:
            raise IncompleteRead(b"partial", 2)
        return b"format,qid\nhttp://www.wikidata.org/entity/Q1,Q1\n", {"content-type": "text/csv"}

    monkeypatch.setattr(WikidataSparqlAdapter, "_request_csv", flaky_request)
    monkeypatch.setattr("registry_builder.wikidata_download.time.sleep", lambda seconds: None)

    adapter = _TransportRetryingWikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "transport_retries": 2,
            "transport_backoff_seconds": 0,
        },
        tmp_path / "work",
    )

    data, headers = adapter._request_csv(
        "SELECT ?format ?qid WHERE {}",
        query_name="core",
        required_columns={"format", "qid"},
    )

    assert calls["count"] == 2
    assert data.startswith(b"format,qid")
    assert headers["content-type"] == "text/csv"
