from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from registry_builder.models import SourceSnapshot
from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.wikidata_refresh_simulation import (
    build_remove_one_relationship_snapshot,
    run_wikidata_changed_source_simulation,
)
from registry_builder.wikidata_relationship_backfill import (
    WIKIDATA_EVIDENCE_PROJECTION_VERSION,
    WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
    WIKIDATA_SOURCE_ID,
    _decorate_claim,
)


CANONICAL_ID = "puid-fmt-1"


def _write_source(path: Path) -> None:
    path.write_text(
        "qid,formatLabel,instanceOfQid,puid,locFdd,naraFormatPlanId\n"
        "Q1,Format One,Q235557,fmt/1,,\n"
        "Q2,Unlinked Format,Q235557,,,\n",
        encoding="utf-8",
    )


def _snapshot(path: Path) -> SourceSnapshot:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return SourceSnapshot(
        source_id=WIKIDATA_SOURCE_ID,
        source_type="wikidata_sparql_evidence",
        uri="https://query.wikidata.org/sparql",
        acquired_at="2026-08-21T00:00:00Z",
        sha256=digest,
        local_path=str(path),
        content_type="text/csv",
        changed=False,
        from_cache=True,
        metadata={"population_policy_version": "2026-08-20-v3"},
    )


def _edge() -> dict:
    return {
        "canonical_id": CANONICAL_ID,
        "source_id": WIKIDATA_SOURCE_ID,
        "source_type": "wikidata_sparql",
        "source_record_id": "Q1",
        "wikidata_role": "format",
        "relationship": "explicit_wikidata_identifier_cross_reference",
        "evidence_scope": "single_canonical_cross_reference",
        "copied_identifiers": [{"kind": "puid", "value": "fmt/1"}],
        "source_url": "https://www.wikidata.org/wiki/Q1",
    }


def _seed_verified_baseline(store: MemoryRegistryStore) -> None:
    store.upsert_canonical_format(
        {
            "canonical_id": CANONICAL_ID,
            "format_id": CANONICAL_ID,
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
            "source_records": [
                {
                    "source_id": WIKIDATA_SOURCE_ID,
                    "source_type": "wikidata_sparql",
                    "source_record_id": "Q1",
                    "relationship": "explicit_wikidata_identifier_cross_reference",
                    "evidence_scope": "single_canonical_cross_reference",
                    "persistence_layer": "source_relationship_claims",
                    "identifier_cross_references": [
                        {"kind": "puid", "value": "fmt/1"}
                    ],
                    "projection_version": WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
                }
            ],
            "current": True,
            "run_id": "canonical-baseline",
            "last_seen_run_id": "canonical-baseline",
        }
    )
    store.create_run(
        {
            "run_id": "relationship-backfill-baseline",
            "run_kind": "source_relationship_backfill",
            "started_at": "2026-08-20T00:00:00Z",
            "finished_at": "2026-08-20T00:00:01Z",
            "status": "completed",
            "relationship_source_id": WIKIDATA_SOURCE_ID,
            "sources": [
                {
                    "source_id": WIKIDATA_SOURCE_ID,
                    "source_type": "wikidata_sparql",
                    "status": "completed",
                    "records_extracted": 2,
                    "snapshots": 1,
                }
            ],
        }
    )
    for qid, name in (("Q1", "Format One"), ("Q2", "Unlinked Format")):
        store.save_source_record(
            {
                "run_id": "relationship-backfill-baseline",
                "source_id": WIKIDATA_SOURCE_ID,
                "source_type": "wikidata_sparql",
                "source_record_id": qid,
                "record_role": "evidence_only",
                "name": name,
                "identifiers": [],
                "risk_assessments": [],
                "native_fields": {
                    "evidence_projection_version": WIKIDATA_EVIDENCE_PROJECTION_VERSION,
                },
            }
        )
    claim = _decorate_claim(_edge())
    claim.update(
        {
            "run_id": "relationship-backfill-baseline",
            "current": True,
            "last_seen_run_id": "relationship-backfill-baseline",
        }
    )
    store.upsert("source_relationship_claims", claim["claim_id"], claim)


def _source_config() -> dict:
    return {
        "id": WIKIDATA_SOURCE_ID,
        "type": "wikidata_sparql_evidence",
    }


def _permissive_drift_gates() -> dict:
    return {
        "max_population_change_absolute": 100,
        "max_population_change_fraction": 10.0,
        "max_relationship_edge_change_absolute": 100,
        "max_relationship_edge_change_fraction": 10.0,
        "max_claim_turnover_absolute": 100,
        "max_claim_turnover_fraction": 10.0,
    }


def test_simulation_snapshot_removes_one_authority_value_without_population_change(tmp_path):
    source = tmp_path / "wikidata.csv"
    target = tmp_path / "simulated.csv"
    _write_source(source)

    snapshot, mutation = build_remove_one_relationship_snapshot(source, target)

    rows = list(csv.DictReader(target.open("r", encoding="utf-8", newline="")))
    assert len(rows) == 2
    assert mutation == {
        "qid": "Q1",
        "field": "puid",
        "identifier_kind": "puid",
        "identifier_value_removed": "fmt/1",
    }
    assert rows[0]["qid"] == "Q1"
    assert rows[0]["puid"] == ""
    assert rows[1]["qid"] == "Q2"
    assert snapshot.changed is True
    assert snapshot.from_cache is False
    assert snapshot.metadata["simulation"] is True


def test_changed_source_simulation_is_read_only_and_reports_exactly_one_removal(tmp_path):
    source = tmp_path / "wikidata.csv"
    _write_source(source)
    store = MemoryRegistryStore()
    _seed_verified_baseline(store)

    report = run_wikidata_changed_source_simulation(
        store=store,
        source_config=_source_config(),
        workdir=tmp_path / "work",
        output_csv=tmp_path / "simulated.csv",
        drift_gates=_permissive_drift_gates(),
        base_snapshots=[_snapshot(source)],
    )

    assert report["status"] == "ok"
    assert report["errors"] == []
    assert report["registry_writes_performed"] == 0
    assert report["registry_fingerprint_unchanged"] is True
    assert report["mutation"]["qid"] == "Q1"

    preflight = report["preflight"]
    assert preflight["status"] == "ready"
    assert preflight["gate_passed"] is True
    assert preflight["records_acquired"] == 2
    assert preflight["claim_turnover"]["added"] == 0
    assert preflight["claim_turnover"]["removed"] == 1
    assert preflight["claim_turnover"]["turnover"] == 1
    assert preflight["preview"]["relationship_edges"] == 0
    assert preflight["preview"]["unmatched_authority_claims"] == 0
    assert preflight["preview"]["canonical_formats"] == 1
    assert preflight["preview"]["canonical_formats_created"] == 0
    assert preflight["preview"]["canonical_identifiers_promoted"] == 0

    current_claims = [
        row
        for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
    ]
    assert len(current_claims) == 1
    assert current_claims[0]["source_record_id"] == "Q1"
    assert len(store.query("source_records")) == 2
