from pathlib import Path
import json

from registry_builder.pipeline import run_pipeline
from registry_builder.storage.file import FileRegistryStore


WIKIDATA = "wikidata_file_formats"


def test_unrelated_source_refresh_preserves_governed_wikidata_relationship(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_path = tmp_path / "persistent-store"
    config = {
        "pipeline_version": "0.1.0",
        "incremental_source_updates": True,
        "storage": {"type": "file", "path": str(store_path)},
        "exports": {"enabled": False},
        "method_profiles": {"enabled": False},
        "identifier_kinds": {
            "puid": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "loc": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "nara": {"strength": "strong", "verified_from": []},
            "wikidata": {"strength": "weak", "verified_from": []},
        },
        "sources": [
            {
                "id": "qnl_institution_format_evidence_2026_seed",
                "type": "qnl_institution_format_evidence",
                "enabled": True,
                "required": True,
                "institution_id": "qnl",
                "institution_name": "Qatar National Library",
                "uris": [str(repo_root / "examples" / "qnl_institution_format_evidence.seed.json")],
            }
        ],
    }
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    first = run_pipeline(config_path, tmp_path / "work", tmp_path / "out-1")
    assert first["canonical_formats"] > 0

    store = FileRegistryStore({"path": str(store_path)})
    target = store.get_current_registry_view()[0]
    canonical_id = target["canonical_id"]
    identifiers_before = target.get("identifiers") or {}

    claim = {
        "claim_id": "src-rel-lifecycle-q999",
        "canonical_id": canonical_id,
        "source_id": WIKIDATA,
        "source_type": "wikidata_sparql",
        "source_record_id": "Q999",
        "wikidata_role": "format",
        "relationship": "explicit_wikidata_identifier_cross_reference",
        "evidence_scope": "single_canonical_cross_reference",
        "copied_identifiers": [{"kind": "puid", "value": "fmt/9999"}],
        "source_url": "https://www.wikidata.org/wiki/Q999",
        "projection_version": "2026-08-21-v1-authority-cross-reference",
        "identity_projection": False,
        "identifier_promotion": False,
        "run_id": "relationship-backfill-seed",
        "current": True,
        "last_seen_run_id": "relationship-backfill-seed",
    }
    store.upsert("source_relationship_claims", claim["claim_id"], claim)

    second = run_pipeline(config_path, tmp_path / "work", tmp_path / "out-2")

    governed = second["risk_claim_materialization"]["source_relationship_materialization"]
    assert governed["current_claims_loaded"] == 1
    assert governed["relationships_materialized"] == 1
    assert governed["canonicals_with_materialized_relationships"] == 1
    assert governed["orphan_claims"] == 0
    assert governed["invalid_claims"] == 0
    assert governed["refreshed_claim_sources"] == []
    assert governed["source_backfill_refresh_recommended"] is False
    assert governed["claim_sources"] == {WIKIDATA: 1}
    assert governed["identity_projection"] is False
    assert governed["identifier_promotion"] is False

    refreshed = FileRegistryStore({"path": str(store_path)})
    current = refreshed.query("canonical_formats", {"canonical_id": canonical_id})[0]
    wikidata_refs = [
        item
        for item in (current.get("source_records") or [])
        if item.get("source_id") == WIKIDATA
        and item.get("source_record_id") == "Q999"
    ]

    assert len(wikidata_refs) == 1
    ref = wikidata_refs[0]
    assert ref["persistence_layer"] == "source_relationship_claims"
    assert ref["relationship"] == "explicit_wikidata_identifier_cross_reference"
    assert ref["evidence_scope"] == "single_canonical_cross_reference"
    assert ref["identifier_cross_references"] == [{"kind": "puid", "value": "fmt/9999"}]
    assert current.get("identifiers") == identifiers_before
    assert second["canonical_formats"] == first["canonical_formats"]
