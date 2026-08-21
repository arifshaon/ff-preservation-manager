import json
from pathlib import Path

from registry_builder.nara_risk_assessment_preview import build_nara_risk_inventory
from registry_builder.storage.memory import MemoryRegistryStore


ROOT = Path(__file__).resolve().parents[1]


def _store():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-nara",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": "nara_digital_preservation_framework", "status": "completed"}],
    })
    store.save_source_record({
        "run_id": "run-nara",
        "source_id": "nara_digital_preservation_framework",
        "source_type": "nara_digital_preservation_framework",
        "source_record_id": "NF00371",
        "name": "PDF/A-1a",
    })
    store.upsert_canonical_format({
        "canonical_id": "nara-nf00371",
        "preferred_name": "Portable Document Format/Archiving (PDF/A-1a) accessible",
        "current": True,
        "source_records": [
            {
                "source_id": "nara_digital_preservation_framework",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00371",
            }
        ],
        "external_hazard": [
            {
                "source": "NARA Digital Preservation Framework",
                "source_type": "nara_digital_preservation_framework",
                "native_band": "Low Risk",
                "external_rating_native": 36.0,
                "external_rating_native_scale": "nara_file_format_risk_matrix",
                "band": "Low",
                "rating": 1.0,
            }
        ],
        "risk_assessments": [],
        "synthesized_risk": {},
    })
    return store


def test_nara_preview_projects_native_risk_without_writing():
    store = _store()

    report = build_nara_risk_inventory(store)

    assert report["mode"] == "read_only_store_preview"
    assert report["storage_write"] is False
    assert report["identity_projection"] is False
    assert report["latest_source_run_id"] == "run-nara"
    assert report["latest_nara_source_record_count"] == 1
    assert report["projected_claim_count"] == 1
    assert report["canonical_formats_with_nara_assessment"] == 1
    assert report["assessments_missing_source_record_id"] == 0
    assert report["canonical_formats_with_multiple_nara_assessments"] == 0
    assert report["nara_source_records_targeting_multiple_canonicals"] == 0
    assert report["current_persisted_nara_claims"] == 0
    assert report["semantic_levels"] == {"low": 1}
    assert report["native_labels"] == {"Low Risk": 1}
    assert report["native_scales"] == {"nara_file_format_risk_matrix": 1}
    assert report["scope_types"] == {"exact_format": 1}
    claim = report["sample_claims"][0]
    assert claim["source_record_id"] == "NF00371"
    assert claim["source_record_id_basis"] == "single_canonical_nara_source_record"
    assert claim["native_score"] == 36.0
    assert claim["semantic_level"] == "low"

    assert store.query("risk_assessment_claims") == []


def test_nara_only_config_keeps_puid_authority_with_pronom():
    config = json.loads((ROOT / "config" / "sources.qnl.nara-only.json").read_text(encoding="utf-8"))

    assert config["identifier_kinds"]["puid"]["verified_from"] == [
        "pronom_registry",
        "pronom_droid_xml",
    ]
