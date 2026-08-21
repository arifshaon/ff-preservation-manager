from pathlib import Path

from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.wikidata_relationship_backfill import run_wikidata_relationship_backfill


def _write_csv(path: Path) -> None:
    path.write_text(
        "qid,formatLabel,instanceOfQid,puid\n"
        "Q1,Format One,Q235557,fmt/1\n"
        "Q2,Unlinked Format,Q235557,\n",
        encoding="utf-8",
    )


def test_backfill_persists_evidence_only_records_and_relationship_claims(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)

    store = MemoryRegistryStore()
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-1",
        "format_id": "puid-fmt-1",
        "preferred_name": "Format One",
        "identifiers": {"puid": ["fmt/1"]},
        "identifier_claims": [
            {
                "kind": "puid",
                "value": "fmt/1",
                "source": "pronom_registry",
                "verified": True,
                "source_record_id": "fmt/1",
            }
        ],
        "source_records": [],
        "current": True,
        "run_id": "baseline-run",
        "last_seen_run_id": "baseline-run",
    })

    report = run_wikidata_relationship_backfill(
        store=store,
        input_csv=csv_path,
        dry_run=False,
        expected_counts={
            "canonical_formats": 1,
            "wikidata_records": 2,
            "wikidata_qids_with_relationships": 1,
            "canonical_formats_with_wikidata_relationships": 1,
            "relationship_edges": 1,
            "matched_authority_claims": 1,
        },
        max_unmatched_authority_claims=0,
    )

    assert report["migration_gate_passed"] is True
    assert report["source_records_written"] == 2
    assert report["claims_written"] == 1
    assert report["canonical_records_updated"] == 1

    stored_source_records = store.query("source_records")
    assert len(stored_source_records) == 2
    assert {row["source_record_id"] for row in stored_source_records} == {"Q1", "Q2"}
    assert {row["record_role"] for row in stored_source_records} == {"evidence_only"}

    claims = store.query("source_relationship_claims")
    assert len(claims) == 1
    assert claims[0]["canonical_id"] == "puid-fmt-1"
    assert claims[0]["source_record_id"] == "Q1"
    assert claims[0]["current"] is True

    current = store.get_current_registry_view()
    assert len(current) == 1
    assert current[0]["identifiers"] == {"puid": ["fmt/1"]}
    refs = [
        ref for ref in current[0]["source_records"]
        if ref.get("persistence_layer") == "source_relationship_claims"
    ]
    assert len(refs) == 1
    assert refs[0]["source_record_id"] == "Q1"
    assert refs[0]["identifier_cross_references"] == [
        {"kind": "puid", "value": "fmt/1"}
    ]


def test_backfill_gate_blocks_writes_on_count_drift(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)
    store = MemoryRegistryStore()
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-1",
        "preferred_name": "Format One",
        "identifiers": {"puid": ["fmt/1"]},
        "current": True,
    })

    report = run_wikidata_relationship_backfill(
        store=store,
        input_csv=csv_path,
        dry_run=False,
        expected_counts={"wikidata_records": 999},
        max_unmatched_authority_claims=0,
    )

    assert report["status"] == "blocked"
    assert report["migration_gate_passed"] is False
    assert store.query("source_records") == []
    assert store.query("source_relationship_claims") == []
