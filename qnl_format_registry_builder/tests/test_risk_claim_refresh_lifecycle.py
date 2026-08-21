from pathlib import Path
import json

from registry_builder.pipeline import run_pipeline
from registry_builder.risk_synthesis import synthesize_risk_assessments
from registry_builder.storage.file import FileRegistryStore


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


def test_source_only_refresh_preserves_dpc_and_nara_claim_layers(tmp_path):
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
    dpc_claim = _dpc_claim(canonical_id)
    nara_claim = _nara_claim(canonical_id)
    store.upsert("risk_assessment_claims", "dpc|pipeline-target", dpc_claim)
    store.upsert("risk_assessment_claims", "nara|pipeline-target", nara_claim)

    # Emulate the state immediately after reviewed DPC/NARA backfills. The next
    # unrelated source refresh must rebuild canonical identity and then restore
    # both governed claim layers from risk_assessment_claims.
    target["risk_assessments"] = [
        dict(dpc_claim["assessment"], persistence_layer="risk_assessment_claims"),
        dict(nara_claim["assessment"], persistence_layer="risk_assessment_claims"),
    ]
    target["provenance"] = dict(target.get("provenance") or {}) | {
        "materialized_risk_claim_sources": [DPC, NARA],
        "risk_claim_materialization": "risk_assessment_claims",
    }
    target["synthesized_risk"] = synthesize_risk_assessments(target["risk_assessments"])
    store.upsert_canonical_format(target)

    second = run_pipeline(config_path, tmp_path / "work", tmp_path / "out-2")

    materialization = second["risk_claim_materialization"]
    assert materialization["current_claims_loaded"] == 2
    assert materialization["claims_materialized"] == 2
    assert materialization["canonicals_with_materialized_claims"] == 1
    assert materialization["orphan_claims"] == 0
    assert materialization["invalid_claims"] == 0
    assert materialization["refreshed_claim_sources"] == []
    assert materialization["source_backfill_refresh_recommended"] is False
    assert materialization["claim_sources"] == {DPC: 1, NARA: 1}

    refreshed = FileRegistryStore({"path": str(store_path)})
    current = refreshed.query("canonical_formats", {"canonical_id": canonical_id})[0]
    assessments = current.get("risk_assessments") or []
    dpc = [item for item in assessments if item.get("source_id") == DPC]
    nara = [item for item in assessments if item.get("source_id") == NARA]

    assert len(dpc) == 1
    assert len(nara) == 1
    assert dpc[0]["persistence_layer"] == "risk_assessment_claims"
    assert nara[0]["persistence_layer"] == "risk_assessment_claims"
    assert current["synthesized_risk"]["semantic_level"] == "low"
    assert current["synthesized_risk"]["selected_scope_tier"] == "exact_or_version"
    assert current["synthesized_risk"]["contextual_levels"] == ["moderate"]
    assert second["canonical_formats"] == first["canonical_formats"]
