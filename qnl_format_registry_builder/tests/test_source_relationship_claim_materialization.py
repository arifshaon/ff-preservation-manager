from registry_builder.models import CanonicalFormat
from registry_builder.source_relationship_claim_materialization import (
    PERSISTENCE_LAYER,
    materialize_current_source_relationship_claims,
)
from registry_builder.storage.memory import MemoryRegistryStore


def _claim(canonical_id="puid-fmt-1", qid="Q1"):
    return {
        "claim_id": f"claim-{canonical_id}-{qid}",
        "canonical_id": canonical_id,
        "source_id": "wikidata_file_formats",
        "source_type": "wikidata_sparql",
        "source_record_id": qid,
        "relationship": "explicit_wikidata_identifier_cross_reference",
        "evidence_scope": "single_canonical_cross_reference",
        "copied_identifiers": [{"kind": "puid", "value": "fmt/1"}],
        "wikidata_role": "format",
        "source_url": f"https://www.wikidata.org/wiki/{qid}",
        "projection_version": "test-v1",
        "current": True,
        "run_id": "relationship-run-1",
    }


def test_materialization_is_idempotent_and_does_not_touch_identifiers():
    store = MemoryRegistryStore()
    store.upsert("source_relationship_claims", "claim-1", _claim())
    fmt = CanonicalFormat(
        canonical_id="puid-fmt-1",
        preferred_name="Format One",
        identifiers={"puid": ["fmt/1"]},
        source_records=[
            {
                "source_id": "pronom_registry",
                "source_type": "pronom_registry",
                "source_record_id": "fmt/1",
            }
        ],
    )

    first = materialize_current_source_relationship_claims([fmt], store)
    second = materialize_current_source_relationship_claims([fmt], store)

    wikidata_refs = [
        ref for ref in fmt.source_records
        if ref.get("persistence_layer") == PERSISTENCE_LAYER
    ]
    assert len(wikidata_refs) == 1
    assert wikidata_refs[0]["identifier_cross_references"] == [
        {"kind": "puid", "value": "fmt/1"}
    ]
    assert fmt.identifiers == {"puid": ["fmt/1"]}
    assert first["relationships_materialized"] == 1
    assert second["relationships_materialized"] == 1
    assert second["identity_projection"] is False
    assert second["identifier_promotion"] is False


def test_orphan_claim_is_reported_without_identity_creation():
    store = MemoryRegistryStore()
    store.upsert(
        "source_relationship_claims",
        "orphan",
        _claim(canonical_id="missing-canonical", qid="Q2"),
    )
    fmt = CanonicalFormat(canonical_id="puid-fmt-1", preferred_name="Format One")

    result = materialize_current_source_relationship_claims([fmt], store)

    assert result["orphan_claims"] == 1
    assert result["relationships_materialized"] == 0
    assert fmt.source_records == []


def test_refreshed_relationship_source_is_flagged_for_backfill_refresh():
    store = MemoryRegistryStore()
    store.upsert("source_relationship_claims", "claim-1", _claim())
    fmt = CanonicalFormat(canonical_id="puid-fmt-1", preferred_name="Format One")

    result = materialize_current_source_relationship_claims(
        [fmt],
        store,
        refreshed_source_ids={"wikidata_file_formats"},
    )

    assert result["refreshed_claim_sources"] == ["wikidata_file_formats"]
    assert result["source_backfill_refresh_recommended"] is True
