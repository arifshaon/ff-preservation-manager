from __future__ import annotations

from pathlib import Path

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.wikidata_sparql_evidence import (
    WIKIDATA_EVIDENCE_PROJECTION_VERSION,
    WIKIDATA_RECORD_SOURCE_TYPE,
    WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
    WikidataSparqlEvidenceAdapter,
)
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot
from registry_builder.reconcile import reconcile


def _snapshot(path: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="wikidata_file_formats",
        source_type="wikidata_sparql_evidence",
        uri=str(path),
        acquired_at="2026-08-21T00:00:00Z",
        sha256="test",
        local_path=str(path),
        content_type="text/csv",
        note="test",
        changed=True,
        from_cache=False,
        metadata={},
    )


def _write_csv(path: Path) -> None:
    path.write_text(
        "qid,formatLabel,instanceOfQid,puid,locFdd,naraFormatPlanId,extension,mimeType\n"
        "Q1,Format One,Q235557,fmt/1,,,one,application/x-one\n"
        "Q2,Compression Context,Q7927899,,fdd000002,NF00002,,\n",
        encoding="utf-8",
    )


def test_production_adapter_is_registered():
    assert resolve_adapter("wikidata_sparql_evidence") is WikidataSparqlEvidenceAdapter


def test_extract_forces_all_wikidata_rows_to_evidence_only(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)
    adapter = WikidataSparqlEvidenceAdapter(
        {"id": "wikidata_file_formats", "type": "wikidata_sparql_evidence"},
        tmp_path / "work",
    )

    records = adapter.extract([_snapshot(csv_path)])
    by_qid = {record.source_record_id: record for record in records}

    assert set(by_qid) == {"Q1", "Q2"}
    assert {record.record_role for record in records} == {"evidence_only"}
    assert by_qid["Q1"].native_fields["wikidata_role"] == "format"
    assert by_qid["Q2"].native_fields["wikidata_role"] == "codec_or_encoding"
    assert {record.source_type for record in records} == {WIKIDATA_RECORD_SOURCE_TYPE}

    for record in records:
        assert record.native_fields["identity_projection"] is False
        assert record.native_fields["identifier_promotion"] is False
        assert record.native_fields["evidence_projection_version"] == WIKIDATA_EVIDENCE_PROJECTION_VERSION
        assert record.native_fields["relationship_projection_version"] == WIKIDATA_RELATIONSHIP_PROJECTION_VERSION
        assert record.risk_assessments == []

    q1_identifiers = {
        (identifier.kind, identifier.value, identifier.verified)
        for identifier in by_qid["Q1"].identifiers
    }
    assert ("wikidata", "Q1", True) in q1_identifiers
    assert ("puid", "fmt/1", False) in q1_identifiers

    q2_identifiers = {
        (identifier.kind, identifier.value, identifier.verified)
        for identifier in by_qid["Q2"].identifiers
    }
    assert ("loc", "fdd000002", False) in q2_identifiers
    assert ("nara", "NF00002", False) in q2_identifiers


def test_evidence_adapter_cannot_create_or_merge_canonical_identity(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)
    adapter = WikidataSparqlEvidenceAdapter(
        {"id": "wikidata_file_formats", "type": "wikidata_sparql_evidence"},
        tmp_path / "work",
    )
    wikidata_records = adapter.extract([_snapshot(csv_path)])

    pronom = RawFormatRecord(
        source_id="pronom_registry",
        source_type="pronom_registry",
        source_record_id="fmt/1",
        record_role="format_identity",
        name="Format One Authority",
        identifiers=[
            Identifier(
                kind="puid",
                value="fmt/1",
                source="pronom_registry",
                verified=True,
                source_record_id="fmt/1",
            )
        ],
        puids=["fmt/1"],
    )

    registry = reconcile([pronom, *wikidata_records])

    assert len(registry) == 1
    assert registry[0].canonical_id == "puid-fmt-1"
    assert registry[0].identifiers.get("puid") == ["fmt/1"]
    assert not registry[0].identifiers.get("wikidata")
    assert all(
        ref.get("source_id") != "wikidata_file_formats"
        for ref in registry[0].source_records
    )
