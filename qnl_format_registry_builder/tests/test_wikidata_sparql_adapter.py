from __future__ import annotations

import csv
import io
import re
from urllib.parse import parse_qs

import pytest

from registry_builder.adapters.wikidata_sparql import (
    DEFAULT_QUERY_PARTS,
    POPULATION_QUERY_TEMPLATES,
    WikidataSparqlAdapter,
)


def _csv_bytes(fields: list[str], rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _qids_from_values(query: str) -> list[str]:
    return re.findall(r"\bwd:(Q\d+)\b", query)


def _fake_staged_request_factory(*, fail_once: str | None = None, calls=None):
    state = {"failed": False}
    calls = calls if calls is not None else []

    def fake_request(self, query, *, query_name, required_columns):
        calls.append(query_name)

        if fail_once == query_name and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("simulated interruption")

        if query_name == "population:taxonomy:page:1":
            return _csv_bytes(
                ["format"],
                [
                    {"format": "http://www.wikidata.org/entity/Q100"},
                    {"format": "http://www.wikidata.org/entity/Q200"},
                ],
            ), {"content-type": "text/csv"}
        if query_name == "population:taxonomy:page:2":
            return _csv_bytes(["format"], []), {"content-type": "text/csv"}
        if query_name == "population:pronom_linked:page:1":
            return _csv_bytes(
                ["format"],
                [{"format": "http://www.wikidata.org/entity/Q300"}],
            ), {"content-type": "text/csv"}

        qids = _qids_from_values(query)
        if query_name.startswith("core:batch:"):
            return _csv_bytes(
                ["format", "qid", "formatLabel", "formatDescription"],
                [
                    {
                        "format": f"http://www.wikidata.org/entity/{qid}",
                        "qid": qid,
                        "formatLabel": f"Format {qid}",
                        "formatDescription": f"Description {qid}",
                    }
                    for qid in qids
                ],
            ), {"content-type": "text/csv"}

        if query_name.startswith("aliases:batch:"):
            return _csv_bytes(
                ["format", "alias"],
                [
                    {
                        "format": f"http://www.wikidata.org/entity/{qid}",
                        "alias": f"Alias {qid}",
                    }
                    for qid in qids
                ],
            ), {"content-type": "text/csv"}

        if query_name.startswith("classification:batch:"):
            return _csv_bytes(
                ["format", "predicate", "value", "valueLabel"],
                [
                    {
                        "format": f"http://www.wikidata.org/entity/{qid}",
                        "predicate": "http://www.wikidata.org/prop/direct/P31",
                        "value": "http://www.wikidata.org/entity/Q235557",
                        "valueLabel": "file format",
                    }
                    for qid in qids
                ],
            ), {"content-type": "text/csv"}

        if query_name.startswith("identifiers:batch:"):
            rows = []
            for qid in qids:
                if qid == "Q100":
                    rows.append(
                        {
                            "format": "http://www.wikidata.org/entity/Q100",
                            "predicate": "http://www.wikidata.org/prop/direct/P2748",
                            "value": "fmt/1",
                        }
                    )
                elif qid == "Q200":
                    rows.append(
                        {
                            "format": "http://www.wikidata.org/entity/Q200",
                            "predicate": "http://www.wikidata.org/prop/direct/P3266",
                            "value": "fdd000200",
                        }
                    )
                elif qid == "Q300":
                    rows.append(
                        {
                            "format": "http://www.wikidata.org/entity/Q300",
                            "predicate": "http://www.wikidata.org/prop/direct/P11167",
                            "value": "NF00300",
                        }
                    )
            return _csv_bytes(["format", "predicate", "value"], rows), {
                "content-type": "text/csv"
            }

        if query_name.startswith("technical_literals:batch:"):
            return _csv_bytes(
                ["format", "predicate", "value"],
                [
                    {
                        "format": f"http://www.wikidata.org/entity/{qid}",
                        "predicate": "http://www.wikidata.org/prop/direct/P1195",
                        "value": qid.lower(),
                    }
                    for qid in qids
                ],
            ), {"content-type": "text/csv"}

        if query_name.startswith("item_relations:batch:"):
            return _csv_bytes(
                ["format", "predicate", "value", "valueLabel"],
                [
                    {
                        "format": f"http://www.wikidata.org/entity/{qid}",
                        "predicate": "http://www.wikidata.org/prop/direct/P178",
                        "value": "http://www.wikidata.org/entity/Q999",
                        "valueLabel": "Example Developer",
                    }
                    for qid in qids
                ],
            ), {"content-type": "text/csv"}

        raise AssertionError(f"Unexpected query: {query_name}")

    return fake_request


def test_default_queries_use_correct_file_format_properties_and_values_batches():
    population_text = "\n".join(POPULATION_QUERY_TEMPLATES.values())
    batch_text = "\n".join(DEFAULT_QUERY_PARTS.values())

    assert "wdt:P2748" in population_text
    assert "wdt:P31/wdt:P279* wd:Q235557" in population_text
    assert "wdt:P2749" not in population_text

    assert "wdt:P2748" in batch_text
    assert "wdt:P3266" in batch_text
    assert "wdt:P11167" in batch_text
    assert "wdt:P4152" in batch_text
    assert "wdt:P2749" not in batch_text
    assert "wdt:P3267" not in batch_text
    assert "VALUES ?format { __VALUES__ }" in batch_text


def test_staged_acquisition_freezes_population_and_batches_properties(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        WikidataSparqlAdapter,
        "_request_csv",
        _fake_staged_request_factory(calls=calls),
    )

    adapter = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "batch_size": 2,
            "population_page_size": 2,
        },
        tmp_path / "work",
    )
    output = tmp_path / "wikidata-file-formats.csv"
    snapshot = adapter.download_to(output)

    rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
    assert [row["qid"] for row in rows] == ["Q100", "Q200", "Q300"]
    assert rows[0]["puid"] == "fmt/1"
    assert rows[1]["locFdd"] == "fdd000200"
    assert rows[2]["naraFormatPlanId"] == "NF00300"
    assert rows[0]["developerQid"] == "Q999"
    assert rows[0]["developerLabel"] == "Example Developer"

    staged = snapshot.metadata["staged_acquisition"]
    assert staged["population_count"] == 3
    assert staged["batch_size"] == 2
    assert staged["total_batches"] == 2
    assert staged["resumed"] is False
    assert staged["parts"]["core"]["batches"] == 2
    assert staged["parts"]["core"]["network_fetches"] == 2

    assert calls.count("population:taxonomy:page:1") == 1
    assert calls.count("population:taxonomy:page:2") == 1
    assert calls.count("population:pronom_linked:page:1") == 1
    assert adapter.extract([snapshot]) == []


def test_interrupted_acquisition_resumes_frozen_population_and_cached_batches(
    tmp_path, monkeypatch
):
    workdir = tmp_path / "work"
    first_calls = []
    monkeypatch.setattr(
        WikidataSparqlAdapter,
        "_request_csv",
        _fake_staged_request_factory(
            fail_once="core:batch:2",
            calls=first_calls,
        ),
    )
    first = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "batch_size": 2,
            "population_page_size": 2,
        },
        workdir,
    )

    with pytest.raises(RuntimeError, match="simulated interruption"):
        first.download_to(tmp_path / "first.csv")

    second_calls = []
    monkeypatch.setattr(
        WikidataSparqlAdapter,
        "_request_csv",
        _fake_staged_request_factory(calls=second_calls),
    )
    second = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "batch_size": 2,
            "population_page_size": 2,
        },
        workdir,
    )
    snapshot = second.download_to(tmp_path / "second.csv")

    assert not any(name.startswith("population:") for name in second_calls)
    assert "core:batch:1" not in second_calls
    assert "core:batch:2" in second_calls

    staged = snapshot.metadata["staged_acquisition"]
    assert staged["resumed"] is True
    assert staged["parts"]["core"]["cache_hits"] == 1
    assert staged["parts"]["core"]["network_fetches"] == 1


def test_offline_reuses_completed_final_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        WikidataSparqlAdapter,
        "_request_csv",
        _fake_staged_request_factory(),
    )
    workdir = tmp_path / "work"
    online = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "batch_size": 2,
            "population_page_size": 2,
        },
        workdir,
    )
    online.download_to(tmp_path / "online.csv")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("offline mode must not contact Wikidata")

    monkeypatch.setattr(WikidataSparqlAdapter, "_request_csv", fail_if_called)
    offline = WikidataSparqlAdapter(
        {
            "id": "wikidata_file_formats",
            "type": "wikidata_sparql",
            "batch_size": 2,
            "population_page_size": 2,
            "offline": True,
        },
        workdir,
    )
    snapshot = offline.download_to(tmp_path / "offline.csv")

    assert snapshot.from_cache is True
    assert (tmp_path / "offline.csv").read_bytes() == (
        tmp_path / "online.csv"
    ).read_bytes()


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


def test_custom_query_still_uses_single_post_request(tmp_path, monkeypatch):
    custom_query = """
SELECT ?format ?qid WHERE {
  BIND(wd:Q123 AS ?format)
  BIND("Q123" AS ?qid)
}
""".strip()
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _FakeResponse(
            b"format,qid\nhttp://www.wikidata.org/entity/Q123,Q123\n"
        )

    monkeypatch.setattr(
        "registry_builder.adapters.wikidata_sparql.urlopen",
        fake_urlopen,
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
