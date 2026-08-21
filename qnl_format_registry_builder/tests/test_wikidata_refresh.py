from __future__ import annotations

import hashlib
from pathlib import Path

from registry_builder.models import SourceSnapshot
from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.wikidata_relationship_backfill import (
    WIKIDATA_EVIDENCE_PROJECTION_VERSION,
    WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
    WIKIDATA_SOURCE_ID,
    _decorate_claim,
)
from registry_builder.wikidata_refresh import run_wikidata_refresh


CANONICAL_ID = "puid-fmt-1"


def _canonical() -> dict:
    return {
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


def _edge(qid: str) -> dict:
    return {
        "canonical_id": CANONICAL_ID,
        "source_id": WIKIDATA_SOURCE_ID,
        "source_type": "wikidata_sparql",
        "source_record_id": qid,
        "wikidata_role": "format",
        "relationship": "explicit_wikidata_identifier_cross_reference",
        "evidence_scope": "single_canonical_cross_reference",
        "copied_identifiers": [{"kind": "puid", "value": "fmt/1"}],
        "source_url": f"https://www.wikidata.org/wiki/{qid}",
    }


def _seed_verified_baseline(store: MemoryRegistryStore) -> None:
    store.upsert_canonical_format(_canonical())
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
                    "records_extracted": 1,
                    "snapshots": 1,
                }
            ],
        }
    )
    store.save_source_record(
        {
            "run_id": "relationship-backfill-baseline",
            "source_id": WIKIDATA_SOURCE_ID,
            "source_type": "wikidata_sparql",
            "source_record_id": "Q1",
            "record_role": "evidence_only",
            "name": "Old Format One",
            "identifiers": [],
            "risk_assessments": [],
            "native_fields": {
                "evidence_projection_version": WIKIDATA_EVIDENCE_PROJECTION_VERSION,
            },
        }
    )
    claim = _decorate_claim(_edge("Q1"))
    claim.update(
        {
            "run_id": "relationship-backfill-baseline",
            "current": True,
            "last_seen_run_id": "relationship-backfill-baseline",
        }
    )
    store.upsert("source_relationship_claims", claim["claim_id"], claim)


def _snapshot(tmp_path: Path, rows: list[str]) -> SourceSnapshot:
    path = tmp_path / "wikidata.csv"
    text = "qid,formatLabel,instanceOfQid,puid\n" + "\n".join(rows) + "\n"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return SourceSnapshot(
        source_id=WIKIDATA_SOURCE_ID,
        source_type="wikidata_sparql_evidence",
        uri="https://query.wikidata.org/sparql",
        acquired_at="2026-08-21T00:00:00Z",
        sha256=digest,
        local_path=str(path),
        content_type="text/csv",
        changed=True,
        from_cache=False,
        metadata={"population_policy_version": "2026-08-20-v3"},
    )


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


def test_refresh_preflight_reports_relationship_replacement_without_writes(tmp_path):
    store = MemoryRegistryStore()
    _seed_verified_baseline(store)
    snapshot = _snapshot(tmp_path, ["Q2,New Format One,Q235557,fmt/1"])

    report = run_wikidata_refresh(
        store=store,
        source_config=_source_config(),
        workdir=tmp_path / "work",
        apply=False,
        drift_gates=_permissive_drift_gates(),
        snapshots=[snapshot],
    )

    assert report["status"] == "ready"
    assert report["gate_passed"] is True
    assert report["baseline_verification"]["status"] == "ok"
    assert report["claim_turnover"]["added"] == 1
    assert report["claim_turnover"]["removed"] == 1
    assert report["claim_turnover"]["unchanged"] == 0
    assert report["preview"]["canonical_formats_created"] == 0
    assert report["preview"]["canonical_identifiers_promoted"] == 0

    current_claims = [
        row for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
    ]
    assert len(current_claims) == 1
    assert current_claims[0]["source_record_id"] == "Q1"
    assert len(store.query("source_records")) == 1


def test_refresh_apply_supersedes_old_relationship_and_verifies_new_state(tmp_path):
    store = MemoryRegistryStore()
    _seed_verified_baseline(store)
    snapshot = _snapshot(tmp_path, ["Q2,New Format One,Q235557,fmt/1"])

    report = run_wikidata_refresh(
        store=store,
        source_config=_source_config(),
        workdir=tmp_path / "work",
        apply=True,
        drift_gates=_permissive_drift_gates(),
        snapshots=[snapshot],
    )

    assert report["status"] == "completed"
    assert report["backfill"]["status"] == "completed"
    assert report["backfill"]["claims_to_supersede"] == 1
    assert report["backfill"]["claims_superseded"] == 1
    assert report["backfill"]["claims_written"] == 1
    assert report["verification"]["status"] == "ok"
    assert report["verification"]["canonical_formats"] == 1
    assert report["verification"]["wikidata_source_records"] == 1
    assert report["verification"]["wikidata_relationship_claims"] == 1
    assert report["verification"]["promoted_wikidata_strong_identifier_claims"] == 0

    current_claims = [
        row for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
    ]
    assert len(current_claims) == 1
    assert current_claims[0]["source_record_id"] == "Q2"

    current = store.get_current_registry_view()
    assert len(current) == 1
    assert current[0]["identifiers"] == {"puid": ["fmt/1"]}
    refs = [
        ref for ref in current[0]["source_records"]
        if ref.get("persistence_layer") == "source_relationship_claims"
    ]
    assert len(refs) == 1
    assert refs[0]["source_record_id"] == "Q2"


def test_refresh_blocks_excessive_population_drift_before_registry_write(tmp_path):
    store = MemoryRegistryStore()
    _seed_verified_baseline(store)
    snapshot = _snapshot(
        tmp_path,
        [
            "Q1,Format One,Q235557,fmt/1",
            "Q2,Format Two,Q235557,",
            "Q3,Format Three,Q235557,",
        ],
    )

    report = run_wikidata_refresh(
        store=store,
        source_config=_source_config(),
        workdir=tmp_path / "work",
        apply=True,
        drift_gates={
            "max_population_change_absolute": 0,
            "max_population_change_fraction": 0.0,
            "max_relationship_edge_change_absolute": 100,
            "max_relationship_edge_change_fraction": 10.0,
            "max_claim_turnover_absolute": 100,
            "max_claim_turnover_fraction": 10.0,
        },
        snapshots=[snapshot],
    )

    assert report["status"] == "blocked"
    assert report["gate_passed"] is False
    assert any("wikidata_population" in error for error in report["gate_errors"])
    assert len(store.query("source_records")) == 1
    current_claims = [
        row for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
    ]
    assert len(current_claims) == 1
    assert current_claims[0]["source_record_id"] == "Q1"
