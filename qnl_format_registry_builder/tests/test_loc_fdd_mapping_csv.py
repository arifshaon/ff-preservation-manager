from __future__ import annotations

from pathlib import Path

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.loc_fdd_mapping_csv import LocFddMappingCsvAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


_SAMPLE = """FDD,Format Title,PUID,Wikidata QID,PUID Match,QID Match,Notes
fdd000001,WAVE Audio File Format,fmt/6,Q217570,Exact,Exact,Same granularity; compare fmt/999 only as background
fdd000022,TIFF 6,fmt/353,Q27231633,Not exact,Exact,PRONOM does not distinguish TIFF versions
fdd000030,PDF Family,,,No match,,Family-level FDD
"""


def _snapshot(path: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="loc_fdd_mapping_20260713",
        source_type="loc_fdd_mapping_csv",
        uri="https://www.loc.gov/preservation/digital/formats/mappings/fdd-puid-qid-20260713.csv",
        acquired_at="2026-08-21T00:00:00+00:00",
        sha256="abc123",
        local_path=str(path),
        content_type="text/csv",
        metadata={"mapping_date": "20260713", "identity_projection": False},
    )


def test_loc_fdd_mapping_adapter_is_registered():
    assert resolve_adapter("loc_fdd_mapping_csv") is LocFddMappingCsvAdapter


def test_crosswalk_extracts_ids_and_preserves_match_context(tmp_path):
    path = tmp_path / "mapping.csv"
    path.write_text(_SAMPLE, encoding="utf-8")
    adapter = LocFddMappingCsvAdapter(
        {"id": "loc_fdd_mapping_20260713", "type": "loc_fdd_mapping_csv", "mapping_date": "20260713"},
        tmp_path,
    )
    entries = adapter.extract_entries([_snapshot(path)])

    assert len(entries) == 3
    assert entries[0]["fdd_ids"] == ["fdd000001"]
    assert entries[0]["puids"] == ["fmt/6"]
    assert "fmt/999" not in entries[0]["puids"]
    assert entries[0]["wikidata_qids"] == ["Q217570"]
    assert entries[0]["title"] == "WAVE Audio File Format"
    assert entries[0]["mapping_context"]["PUID Match"] == "Exact"
    assert entries[1]["mapping_context"]["PUID Match"] == "Not exact"
    assert entries[1]["mapping_context"]["Notes"] == "PRONOM does not distinguish TIFF versions"


def test_crosswalk_records_are_evidence_only_and_identifier_ownership_is_preserved(tmp_path):
    path = tmp_path / "mapping.csv"
    path.write_text(_SAMPLE, encoding="utf-8")
    adapter = LocFddMappingCsvAdapter(
        {"id": "loc_fdd_mapping_20260713", "type": "loc_fdd_mapping_csv", "mapping_date": "20260713"},
        tmp_path,
    )
    records = adapter.extract([_snapshot(path)])
    assert len(records) == 3
    record = normalize_record(records[0])

    assert record.record_role == "evidence_only"
    claims = {(claim.kind, claim.value): claim.verified for claim in record.identifiers}
    assert claims[("loc", "fdd000001")] is True
    assert claims[("puid", "fmt/6")] is False
    assert claims[("wikidata", "Q217570")] is False
    assert ("puid", "fmt/999") not in claims
    assert reconcile(records) == []
