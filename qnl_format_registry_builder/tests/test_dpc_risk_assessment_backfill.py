from registry_builder.dpc_risk_assessment_backfill import run_dpc_risk_backfill
from registry_builder.models import CanonicalFormat
from registry_builder.risk_synthesis import synthesize_risk_assessments
from registry_builder.storage.memory import MemoryRegistryStore


def _mapping(version="dpc-bit-list-2025-v1", *, matches=True):
    selector = {
        "identifier_values": {"extension": ["pdf" if matches else "notpdf"]},
        "preferred_name_regex": "(?i)(PDF|Portable Document Format)",
    }
    return {
        "mapping_version": version,
        "source_id": "dpc_bit_list_2025",
        "source_type": "dpc_bit_list",
        "rules": [
            {
                "rule_id": "dpc-2025-pdf-family",
                "status": "approved",
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "source_record_id": "Lg7_RYL0UI",
                "source_slug": "pdf",
                "scope_type": "format_group",
                "scope_name": "PDF",
                "target_selector": selector,
            }
        ],
    }


def _store():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-dpc",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": "dpc_bit_list_2025", "status": "completed"}],
    })
    store.save_source_record({
        "run_id": "run-dpc",
        "source_id": "dpc_bit_list_2025",
        "source_type": "dpc_bit_list",
        "source_record_id": "Lg7_RYL0UI",
        "record_role": "evidence_only",
        "name": "PDF",
        "native_fields": {"slug": "pdf"},
        "risk_assessments": [
            {
                "assessment_role": "external",
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "source_record_id": "Lg7_RYL0UI",
                "source_label": "DPC Global Bit List 2025",
                "native_label": "Vulnerable",
                "native_scale": "dpc_global_bit_list_classification",
                "semantic_level": "moderate",
                "scope_type": "format_group",
                "scope_name": "PDF",
                "native_assessment": {"imminence": 1, "effort": 2},
            }
        ],
    })
    exact = {
        "assessment_role": "external",
        "source_id": "nara",
        "source_type": "nara_digital_preservation_framework",
        "source_record_id": "NF-PDFA1",
        "source_label": "NARA",
        "native_label": "Low Risk",
        "semantic_level": "low",
        "scope_type": "exact_format",
        "scope_name": "PDF/A-1a",
    }
    fmt = CanonicalFormat(
        canonical_id="nara-nf00371",
        preferred_name="Portable Document Format/Archiving (PDF/A-1a) accessible",
        identifiers={"extension": ["pdf"], "nara": ["NF00371"]},
        risk_assessments=[exact],
        synthesized_risk=synthesize_risk_assessments([exact]),
    )
    row = fmt.to_dict()
    row["current"] = True
    store.upsert_canonical_format(row)
    return store


def test_dpc_risk_backfill_dry_run_writes_nothing():
    store = _store()

    report = run_dpc_risk_backfill(store=store, mapping=_mapping(), dry_run=True)

    assert report["status"] == "dry_run"
    assert report["claims_generated"] == 1
    assert report["claims_to_supersede"] == 0
    assert report["canonical_records_to_update"] == 1
    assert store.query("risk_assessment_claims") == []
    stored = store.get_current_registry_view()[0]
    assert len(stored["risk_assessments"]) == 1
    assert stored["risk_assessments"][0]["source_id"] == "nara"


def test_dpc_risk_backfill_persists_claim_and_materializes_scope_aware_view():
    store = _store()

    report = run_dpc_risk_backfill(store=store, mapping=_mapping())

    assert report["status"] == "completed"
    assert report["claims_written"] == 1
    assert report["claims_superseded"] == 0
    claims = store.query("risk_assessment_claims")
    assert len(claims) == 1
    claim = claims[0]
    assert claim["current"] is True
    assert claim["mapping_version"] == "dpc-bit-list-2025-v1"
    assert claim["assessment"]["scope_type"] == "format_group"
    assert claim["assessment"]["native_assessment"] == {"imminence": 1, "effort": 2}

    stored = store.get_current_registry_view()[0]
    dpc = next(row for row in stored["risk_assessments"] if row.get("source_id") == "dpc_bit_list_2025")
    assert dpc["native_label"] == "Vulnerable"
    assert stored["synthesized_risk"]["semantic_level"] == "low"
    assert stored["synthesized_risk"]["selected_scope_tier"] == "exact_or_version"
    assert stored["synthesized_risk"]["contextual_levels"] == ["moderate"]
    assert stored["synthesized_risk"]["scope_divergence"] is True


def test_dpc_risk_backfill_source_replacement_supersedes_and_removes_stale_materialization():
    store = _store()
    run_dpc_risk_backfill(store=store, mapping=_mapping())

    report = run_dpc_risk_backfill(
        store=store,
        mapping=_mapping("dpc-bit-list-2025-v2", matches=False),
    )

    assert report["claims_generated"] == 0
    assert report["claims_superseded"] == 1
    current = [row for row in store.query("risk_assessment_claims") if row.get("current", True) is not False]
    assert current == []
    history = store.query("risk_assessment_claims")
    assert len(history) == 1
    assert history[0]["current"] is False
    assert history[0]["superseded_reason"] == "source_replaced_by_risk_backfill"

    stored = store.get_current_registry_view()[0]
    assert all(row.get("source_id") != "dpc_bit_list_2025" for row in stored["risk_assessments"])
    assert stored["synthesized_risk"]["semantic_level"] == "low"
    assert stored["synthesized_risk"]["scope_divergence"] is False
