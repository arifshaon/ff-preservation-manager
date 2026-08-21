from pathlib import Path
import json

from registry_builder.models import CanonicalFormat
from registry_builder.pipeline import run_pipeline
from registry_builder.risk_claim_materialization import materialize_current_risk_claims
from registry_builder.storage.file import FileRegistryStore
from registry_builder.storage.memory import MemoryRegistryStore


DPC = "dpc_bit_list_2025"
NARA = "nara_digital_preservation_framework"


def _dpc_claim(canonical_id: str) -> dict:
    assessment = {
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
    return {
        "canonical_id": canonical_id,
        "source_id": DPC,
        "source_type": "dpc_bit_list",
        "source_record_id": "Lg7_RYL0UI",
        "mapping_rule_id": "dpc-2025-pdf-family",
        "mapping_version": "dpc-bit-list-2025-v1",
        "scope_type": "format_group",
        "scope_name": "PDF",
        "native_label": "Vulnerable",
        "semantic_level": "moderate",
        "assessment": assessment,
        "run_id": "risk-backfill-dpc",
        "current": True,
        "last_seen_run_id": "risk-backfill-dpc",
    }


def _nara_claim(canonical_id: str) -> dict:
    assessment = {
        "assessment_role": "external",
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF00371",
        "source_label": "NARA Digital Preservation Framework",
        "native_label": "Low Risk",
        "native_score": 36.0,
        "native_scale": "nara_file_format_risk_matrix",
        "normalized_band": "Low",
        "normalized_score": 1.0,
        "semantic_level": "low",
        "scope_type": "exact_format",
        "scope_name": "PDF/A-1a",
        "projection_version": "nara-native-risk-v2-source-provenance",
    }
    return {
        "canonical_id": canonical_id,
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF00371",
        "projection_version": "nara-native-risk-v2-source-provenance",
        "scope_type": "exact_format",
        "scope_name": "PDF/A-1a",
        "native_label": "Low Risk",
        "semantic_level": "low",
        "assessment": assessment,
        "run_id": "risk-backfill-nara",
        "current": True,
        "last_seen_run_id": "risk-backfill-nara",
    }


def test_materialization_is_idempotent_and_flags_refreshed_claim_source():
    store = MemoryRegistryStore()
    store.upsert("risk_assessment_claims", "dpc|fmt-pdf", _dpc_claim("fmt-pdf"))
    fmt = CanonicalFormat(canonical_id="fmt-pdf", preferred_name="Portable Document Format")

    first = materialize_current_risk_claims(
        [fmt],
        store,
        refreshed_source_ids={DPC},
    )
    second = materialize_current_risk_claims(
        [fmt],
        store,
        refreshed_source_ids={DPC},
    )

    assert first["current_claims_loaded"] == 1
    assert first["claims_materialized"] == 1
    assert first["canonicals_with_materialized_claims"] == 1
    assert first["refreshed_claim_sources"] == [DPC]
    assert first["source_backfill_refresh_recommended"] is True
    assert first["orphan_claims"] == 0
    assert second["claims_materialized"] == 1
    mapped = [item for item in fmt.risk_assessments if item.get("source_id") == DPC]
    assert len(mapped) == 1
    assert mapped[0]["persistence_layer"] == "risk_assessment_claims"
    assert fmt.synthesized_risk["semantic_level"] == "moderate"
    assert fmt.provenance["materialized_risk_claim_sources"] == [DPC]


def test_materialized_nara_claim_replaces_legacy_nara_view_and_preserves_dpc_context():
    store = MemoryRegistryStore()
    store.upsert("risk_assessment_claims", "nara|fmt-pdfa", _nara_claim("fmt-pdfa"))
    store.upsert("risk_assessment_claims", "dpc|fmt-pdfa", _dpc_claim("fmt-pdfa"))

    legacy_nara_hazard = {
        "source": "NARA Digital Preservation Framework",
        "source_id": NARA,
        "source_type": NARA,
        "native_band": "Moderate Risk",
        "external_native_band": "Moderate Risk",
        "external_rating_native": 0.0,
        "external_rating_native_scale": "nara_file_format_risk_matrix",
        "band": "Moderate",
        "rating": 2.0,
    }
    fmt = CanonicalFormat(
        canonical_id="fmt-pdfa",
        preferred_name="PDF/A-1a",
        external_hazard=[legacy_nara_hazard],
        source_records=[
            {
                "source_id": NARA,
                "source_type": NARA,
                "source_record_id": "NF00371",
            }
        ],
    )

    report = materialize_current_risk_claims([fmt], store)

    assert report["claims_materialized"] == 2
    nara = [item for item in fmt.risk_assessments if item.get("source_id") == NARA]
    dpc = [item for item in fmt.risk_assessments if item.get("source_id") == DPC]
    assert len(nara) == 1
    assert nara[0]["source_record_id"] == "NF00371"
    assert nara[0]["semantic_level"] == "low"
    assert nara[0]["persistence_layer"] == "risk_assessment_claims"
    assert len(dpc) == 1
    assert dpc[0]["semantic_level"] == "moderate"
    assert dpc[0]["scope_type"] == "format_group"
    assert fmt.synthesized_risk["semantic_level"] == "low"
    assert fmt.synthesized_risk["selected_scope_tier"] == "exact_or_version"
    assert fmt.synthesized_risk["contextual_levels"] == ["moderate"]


def test_orphan_current_claim_is_reported_without_creating_identity():
    store = MemoryRegistryStore()
    store.upsert("risk_assessment_claims", "dpc|missing", _dpc_claim("missing-canonical"))
    fmt = CanonicalFormat(canonical_id="fmt-present", preferred_name="Present Format")

    report = materialize_current_risk_claims([fmt], store)

    assert report["current_claims_loaded"] == 1
    assert report["claims_materialized"] == 0
    assert report["orphan_claims"] == 1
    assert report["identity_projection"] is False
    assert fmt.canonical_id == "fmt-present"
    assert fmt.risk_assessments == []


def test_file_store_supports_risk_assessment_claim_collection(tmp_path):
    store = FileRegistryStore({"path": str(tmp_path / "store")})
    claim = _dpc_claim("fmt-pdf")

    store.upsert("risk_assessment_claims", "dpc|fmt-pdf", claim)

    rows = store.query("risk_assessment_claims", {"source_id": DPC})
    assert len(rows) == 1
    assert rows[0]["canonical_id"] == "fmt-pdf"
    assert rows[0]["current"] is True


def test_pipeline_rebuild_rematerializes_current_claim_layer(monkeypatch, tmp_path):
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
    claim = _dpc_claim(canonical_id)
    store.upsert("risk_assessment_claims", "dpc|pipeline-target", claim)

    # Represent the post-backfill state before the next source refresh. The
    # second pipeline run must rebuild identity and recover this governed claim
    # from the separate persistent collection rather than from this canonical.
    target["risk_assessments"] = [
        dict(claim["assessment"], persistence_layer="risk_assessment_claims")
    ]
    target["provenance"] = dict(target.get("provenance") or {}) | {
        "materialized_risk_claim_sources": [DPC],
        "risk_claim_materialization": "risk_assessment_claims",
    }
    from registry_builder.risk_synthesis import synthesize_risk_assessments
    target["synthesized_risk"] = synthesize_risk_assessments(target["risk_assessments"])
    store.upsert_canonical_format(target)

    second = run_pipeline(config_path, tmp_path / "work", tmp_path / "out-2")

    materialization = second["risk_claim_materialization"]
    assert materialization["current_claims_loaded"] == 1
    assert materialization["claims_materialized"] == 1
    assert materialization["canonicals_with_materialized_claims"] == 1
    assert materialization["orphan_claims"] == 0
    assert materialization["refreshed_claim_sources"] == []
    assert materialization["source_backfill_refresh_recommended"] is False

    refreshed = FileRegistryStore({"path": str(store_path)})
    current = refreshed.query("canonical_formats", {"canonical_id": canonical_id})[0]
    dpc = [
        item for item in current.get("risk_assessments") or []
        if item.get("source_id") == DPC
    ]
    assert len(dpc) == 1
    assert dpc[0]["persistence_layer"] == "risk_assessment_claims"
    assert current["synthesized_risk"]["semantic_level"] == "moderate"
    assert second["canonical_formats"] == first["canonical_formats"]
