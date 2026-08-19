import json
from urllib.parse import parse_qs, urlparse

from registry_builder.adapters import ADAPTERS
from registry_builder.adapters.wikidata_sparql import (
    P_LOC_FDD,
    P_PRONOM_FILE_FORMAT,
    WikidataSparqlAdapter,
)
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record


def _binding(**values):
    return {key: {"type": "literal", "value": value} for key, value in values.items()}


def _row(qid, label, puids, **extra):
    row = _binding(itemLabel=label, puids=puids, **extra)
    row["item"] = {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}
    return row


def _snapshot(tmp_path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "wikidata.json"
    path.write_text(json.dumps({"results": {"bindings": rows}}), encoding="utf-8")
    return SourceSnapshot(
        source_id="wikidata_sparql",
        source_type="wikidata_sparql",
        uri="https://query.wikidata.org/sparql?query=...",
        acquired_at="2026-08-19T00:00:00+00:00",
        sha256="deadbeef",
        local_path=str(path),
        content_type="application/sparql-results+json",
        metadata={"anchor_property": P_PRONOM_FILE_FORMAT},
    )


def _adapter(tmp_path, **config):
    return WikidataSparqlAdapter({"id": "wikidata_sparql", "progress": False, **config}, tmp_path)


def test_property_constants_are_the_file_format_ones_not_their_near_neighbours():
    # P2749 is PRONOM *software* ID and P3267 is Flickr user ID. Both return
    # well-formed but near-empty results, so the mistake is silent.
    assert P_PRONOM_FILE_FORMAT == "P2748"
    assert P_LOC_FDD == "P3266"


def test_query_anchors_on_pronom_file_format_id(tmp_path):
    query = _adapter(tmp_path)._query()

    assert f"wdt:{P_PRONOM_FILE_FORMAT} ?puid" in query
    assert f"wdt:{P_LOC_FDD}" in query
    assert "P2749" not in query
    assert "P3267" not in query


def test_request_uri_encodes_the_query_so_a_changed_query_is_a_new_snapshot(tmp_path):
    default_uri = _adapter(tmp_path).request_uri()
    custom_uri = _adapter(tmp_path, query="SELECT ?item WHERE { ?item wdt:P2748 ?puid }").request_uri()

    parsed = urlparse(default_uri)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "query.wikidata.org"
    assert params["format"] == ["json"]
    assert P_PRONOM_FILE_FORMAT in params["query"][0]
    assert custom_uri != default_uri


def test_extracts_identity_links_and_native_context(tmp_path):
    snapshot = _snapshot(tmp_path, [
        _row(
            "Q42332",
            "PDF",
            "fmt/18",
            fdds="fdd000030",
            exts="pdf",
            mimes="application/pdf",
            developers="Adobe Inc.",
            published="1993-06-15T00:00:00Z",
        )
    ])

    record = normalize_record(_adapter(tmp_path).extract([snapshot])[0])

    assert record.source_record_id == "Q42332"
    assert record.name == "PDF"
    assert record.puids == ["fmt/18"]
    assert record.loc_ids == ["fdd000030"]
    assert record.wikidata_ids == ["Q42332"]
    assert record.extensions == ["pdf"]
    assert record.mime_types == ["application/pdf"]
    assert record.urls["wikidata"] == "https://www.wikidata.org/wiki/Q42332"
    assert record.native_fields["wikidata"]["developers"] == ["Adobe Inc."]
    assert record.native_fields["wikidata"]["publication_date"] == "1993-06-15T00:00:00Z"
    assert record.native_fields["wikidata"]["label"] == "PDF"
    assert record.evidence[0]["type"] == "wikidata_sparql"
    assert record.evidence[0]["anchor_property"] == P_PRONOM_FILE_FORMAT
    assert record.evidence[0]["snapshot_sha256"] == "deadbeef"


def test_every_identifier_is_unverified_because_wikidata_owns_no_namespace(tmp_path):
    snapshot = _snapshot(tmp_path, [_row("Q42332", "PDF", "fmt/18", fdds="fdd000030")])

    record = normalize_record(_adapter(tmp_path).extract([snapshot])[0])

    assert {i.kind for i in record.identifiers} == {"wikidata", "puid", "loc"}
    assert all(i.verified is False for i in record.identifiers)
    assert all(i.source_record_id == "Q42332" for i in record.identifiers)


def test_item_asserting_several_puids_is_split_into_one_record_each(tmp_path):
    # Q1003899 "Blend file" asserts fmt/902 and fmt/903. A single record cannot
    # be bridged onto either PRONOM canonical without guessing.
    snapshot = _snapshot(tmp_path, [_row("Q1003899", "Blend file", "fmt/902|fmt/903", exts="blend")])

    records = [normalize_record(r) for r in _adapter(tmp_path).extract([snapshot])]

    assert [r.puids for r in records] == [["fmt/902"], ["fmt/903"]]
    assert [r.source_record_id for r in records] == ["Q1003899:fmt/902", "Q1003899:fmt/903"]
    assert [r.name for r in records] == ["Blend file (fmt/902)", "Blend file (fmt/903)"]
    # The breadth of the original claim stays visible on both halves.
    assert all(r.native_fields["wikidata"]["asserted_puids"] == ["fmt/902", "fmt/903"] for r in records)
    assert all(r.native_fields["wikidata"]["label"] == "Blend file" for r in records)
    assert all(r.wikidata_ids == ["Q1003899"] for r in records)


def test_distinct_items_sharing_a_label_are_qualified_by_puid(tmp_path):
    # Wikidata labels are not unique — seven separate items are called
    # "PowerProject". Unqualified, they group together during reconciliation and
    # then carry conflicting PUID claims, which blocks the bridge.
    snapshot = _snapshot(tmp_path, [
        _row("Q100", "PowerProject", "fmt/1"),
        _row("Q101", "PowerProject", "fmt/2"),
        _row("Q102", "Unique Format", "fmt/3"),
    ])

    records = [normalize_record(r) for r in _adapter(tmp_path).extract([snapshot])]

    assert [r.name for r in records] == [
        "PowerProject (fmt/1)",
        "PowerProject (fmt/2)",
        "Unique Format",
    ]
    # Only the name is qualified; the record IDs stay the bare QIDs because
    # neither item was split.
    assert [r.source_record_id for r in records] == ["Q100", "Q101", "Q102"]


def test_label_ambiguity_is_counted_across_every_snapshot(tmp_path):
    first = _snapshot(tmp_path / "a", [_row("Q100", "PowerProject", "fmt/1")])
    second = _snapshot(tmp_path / "b", [_row("Q101", "PowerProject", "fmt/2")])

    records = [normalize_record(r) for r in _adapter(tmp_path).extract([first, second])]

    assert [r.name for r in records] == ["PowerProject (fmt/1)", "PowerProject (fmt/2)"]


def test_rows_without_a_puid_or_qid_are_dropped(tmp_path):
    no_puid = _row("Q200", "Format with no PRONOM record", "")
    no_qid = _binding(itemLabel="Orphan", puids="fmt/9")
    snapshot = _snapshot(tmp_path, [no_puid, no_qid, _row("Q201", "Kept", "fmt/10")])

    records = _adapter(tmp_path).extract([snapshot])

    assert [r.source_record_id for r in records] == ["Q201"]


def test_adapter_is_registered_under_its_type_name():
    assert ADAPTERS["wikidata_sparql"] is WikidataSparqlAdapter
    assert WikidataSparqlAdapter.type_name == "wikidata_sparql"
