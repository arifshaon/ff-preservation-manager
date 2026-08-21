from registry_builder.nara_risk_assessment_backfill import run_nara_risk_backfill
from registry_builder.storage.memory import MemoryRegistryStore


NARA = "nara_digital_preservation_framework"
DPC = "dpc_bit_list_2025"


def _hazard(label: str, native_rating: float, band: str, normalized_rating: float):
    return {
        "source": "NARA Digital Preservation Framework",
        "source_type": NARA,
        "native_band": label,
        "external_rating_native": native_rating,
        "external_rating_native_scale": "nara_file_format_risk_matrix",
        "external_rating_native_direction": "higher_is_safer",
        "band": band,
        "rating": normalized_rating,
        "normalized_rating": normalized_rating,
    }


def _store():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-nara-1",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": NARA, "status": "completed"}],
    })
    hazard = _hazard("Low Risk", 36.0, "Low", 1.0)
    store.save_source_record({
        "run_id": "run-nara-1",
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF00371",
        "name": "PDF/A-1a",
        "hazard": hazard,
    })
    dpc = {
        "assessment_role": "external",
        "source_id": DPC,
        "source_type": "dpc_bit_list",
        "source_record_id": "Lg7_RYL0UI",
        "source_label": "DPC Global Bit List 2025",
        "native_label": "Vulnerable",
        "native_scale": "dpc_global_bit_list_classification",
        "semantic_level": "moderate",
        "scope_type": "format_group",
        "scope_name": "PDF",
        "mapping_rule_id": "dpc-2025-pdf-family",
        "mapping_version": "dpc-bit-list-2025-v1",
    }
    store.upsert_canonical_format({
        "canonical_id": "nara-nf00371",
        "preferred_name": "Portable Document Format/Archiving (PDF/A-1a) accessible",
        "current": True,
        "identifiers": {"nara": ["NF00371"]},
        "source_records": [
            {"source_id": NARA, "source_type": NARA, "source_record_id": "NF00371"}
        ],
        "external_hazard": [hazard | {"source_id": NARA}],
        "risk_assessments": [dpc],
        "synthesized_risk": {},
        "provenance": {},
    })
    return store


def test_nara_backfill_dry_run_is_gated_and_writes_nothing():
    store = _store()

    report = run_nara_risk_backfill(store=store, dry_run=True)

    assert report["status"] == "dry_run"
    assert report["migration_gate_passed"] is True
    assert report["claims_generated"] == 1
    assert report["current_claims_before"] == 0
    assert report["claims_to_supersede"] == 0
    assert report["canonical_records_to_update"] == 1
    assert report["canonical_headline_changes"] == 1  # fixture starts with no synthesized headline
    assert store.query("risk_assessment_claims") == []
    stored = store.get_current_registry_view()[0]
    assert all(item.get("source_id") != NARA for item in stored.get("risk_assessments") or [])


def test_nara_backfill_persists_source_native_claim_and_preserves_dpc_context():
    store = _store()

    report = run_nara_risk_backfill(store=store)

    assert report["status"] == "completed"
    assert report["claims_written"] == 1
    assert report["claims_superseded"] == 0
    claims = store.query("risk_assessment_claims")
    assert len(claims) == 1
    claim = claims[0]
    assert claim["current"] is True
    assert claim["source_record_id"] == "NF00371"
    assert claim["projection_version"] == "nara-native-risk-v2-source-provenance"
    assert claim["assessment"]["persistence_layer"] == "risk_assessment_claims"

    stored = store.get_current_registry_view()[0]
    nara = [item for item in stored["risk_assessments"] if item.get("source_id") == NARA]
    dpc = [item for item in stored["risk_assessments"] if item.get("source_id") == DPC]
    assert len(nara) == 1
    assert nara[0]["source_record_id"] == "NF00371"
    assert len(dpc) == 1
    assert stored["synthesized_risk"]["semantic_level"] == "low"
    assert stored["synthesized_risk"]["selected_scope_tier"] == "exact_or_version"
    assert stored["synthesized_risk"]["contextual_levels"] == ["moderate"]
    assert stored["provenance"]["materialized_risk_claim_sources"] == [NARA]


def test_nara_backfill_source_replacement_supersedes_previous_projection():
    store = _store()
    run_nara_risk_backfill(store=store)

    store.create_run({
        "run_id": "run-nara-2",
        "finished_at": "2026-08-22T10:00:00Z",
        "sources": [{"source_id": NARA, "status": "completed"}],
    })
    moderate = _hazard("Moderate Risk", 0.0, "Moderate", 2.0)
    store.save_source_record({
        "run_id": "run-nara-2",
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF00999",
        "name": "Replacement format",
        "hazard": moderate,
    })
    row = store.get_current_registry_view()[0]
    row["identifiers"]["nara"] = ["NF00999"]
    row["source_records"] = [
        {"source_id": NARA, "source_type": NARA, "source_record_id": "NF00999"}
    ]
    row["external_hazard"] = [moderate | {"source_id": NARA}]
    # Simulate the canonical rebuilt by the refreshed source pipeline: old
    # materialized NARA claims disappear from the canonical view, while DPC stays.
    row["risk_assessments"] = [
        item for item in row.get("risk_assessments") or []
        if item.get("source_id") != NARA
    ]
    store.upsert_canonical_format(row)

    report = run_nara_risk_backfill(store=store)

    assert report["claims_generated"] == 1
    assert report["claims_superseded"] == 1
    current = [
        item for item in store.query("risk_assessment_claims")
        if item.get("current", True) is not False
    ]
    assert len(current) == 1
    assert current[0]["source_record_id"] == "NF00999"
    history = store.query("risk_assessment_claims")
    old = next(item for item in history if item.get("source_record_id") == "NF00371")
    assert old["current"] is False
    assert old["superseded_reason"] == "source_replaced_by_risk_backfill"


def test_nara_backfill_blocks_write_when_latest_source_record_is_unprojected():
    store = _store()
    store.save_source_record({
        "run_id": "run-nara-1",
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF99999",
        "name": "Unlinked format",
        "hazard": _hazard("High Risk", -40.0, "High", 3.0),
    })

    report = run_nara_risk_backfill(store=store)

    assert report["status"] == "blocked"
    assert report["migration_gate_passed"] is False
    assert report["projection_report"]["latest_source_records_without_projection"] == 1
    assert store.query("risk_assessment_claims") == []
