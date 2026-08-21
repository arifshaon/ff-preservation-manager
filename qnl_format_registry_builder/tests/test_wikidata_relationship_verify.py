from pathlib import Path

from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.wikidata_relationship_backfill import run_wikidata_relationship_backfill
from registry_builder.wikidata_relationship_verify import verify_wikidata_relationship_persistence


def _write_csv(path: Path) -> None:
    path.write_text(
        "qid,formatLabel,instanceOfQid,puid\n"
        "Q1,Format One,Q235557,fmt/1\n"
        "Q2,Unlinked Format,Q235557,\n",
        encoding="utf-8",
    )


def _baseline_store() -> MemoryRegistryStore:
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
    return store


def test_verifier_confirms_complete_evidence_and_relationship_persistence(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)
    store = _baseline_store()

    expected = {
        "canonical_formats": 1,
        "wikidata_records": 2,
        "wikidata_qids_with_relationships": 1,
        "canonical_formats_with_wikidata_relationships": 1,
        "relationship_edges": 1,
        "matched_authority_claims": 1,
    }
    backfill = run_wikidata_relationship_backfill(
        store=store,
        input_csv=csv_path,
        dry_run=False,
        expected_counts=expected,
        max_unmatched_authority_claims=0,
    )
    assert backfill["migration_gate_passed"] is True

    report = verify_wikidata_relationship_persistence(store, expected_counts=expected)

    assert report["status"] == "ok"
    assert report["errors"] == []
    assert report["canonical_formats"] == 1
    assert report["wikidata_source_records"] == 2
    assert report["wikidata_relationship_claims"] == 1
    assert report["wikidata_qids_with_relationships"] == 1
    assert report["canonical_formats_with_wikidata_relationships"] == 1
    assert report["materialized_relationship_edges"] == 1
    assert report["materialized_canonical_formats"] == 1
    assert report["source_record_roles"] == {"evidence_only": 2}
    assert report["promoted_wikidata_strong_identifier_claims"] == 0
    assert report["wikidata_source_records_with_risk_assessments"] == 0


def test_verifier_detects_promoted_wikidata_authority_identifier(tmp_path):
    csv_path = tmp_path / "wikidata.csv"
    _write_csv(csv_path)
    store = _baseline_store()
    expected = {
        "canonical_formats": 1,
        "wikidata_records": 2,
        "wikidata_qids_with_relationships": 1,
        "canonical_formats_with_wikidata_relationships": 1,
        "relationship_edges": 1,
        "matched_authority_claims": 1,
    }
    run_wikidata_relationship_backfill(
        store=store,
        input_csv=csv_path,
        dry_run=False,
        expected_counts=expected,
        max_unmatched_authority_claims=0,
    )

    canonical = store.get_current_registry_view()[0]
    canonical["identifier_claims"].append({
        "kind": "puid",
        "value": "fmt/1",
        "source": "wikidata_file_formats",
        "verified": False,
        "source_record_id": "Q1",
    })
    store.upsert_canonical_format(canonical)

    report = verify_wikidata_relationship_persistence(store, expected_counts=expected)

    assert report["status"] == "failed"
    assert report["promoted_wikidata_strong_identifier_claims"] == 1
    assert any("promoted" in error for error in report["errors"])
