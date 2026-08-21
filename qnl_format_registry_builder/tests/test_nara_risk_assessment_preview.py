import json
from pathlib import Path

from registry_builder.nara_risk_assessment_preview import build_nara_risk_inventory
from registry_builder.storage.memory import MemoryRegistryStore


ROOT = Path(__file__).resolve().parents[1]
NARA = "nara_digital_preservation_framework"


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
        "run_id": "run-nara",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": NARA, "status": "completed"}],
    })
    hazard = _hazard("Low Risk", 36.0, "Low", 1.0)
    store.save_source_record({
        "run_id": "run-nara",
        "source_id": NARA,
        "source_type": NARA,
        "source_record_id": "NF00371",
        "name": "PDF/A-1a",
        "hazard": hazard,
    })
    store.upsert_canonical_format({
        "canonical_id": "nara-nf00371",
        "preferred_name": "Portable Document Format/Archiving (PDF/A-1a) accessible",
        "current": True,
        "identifiers": {"nara": ["NF00371"]},
        "identifier_claims": [
            {
                "kind": "nara",
                "value": "NF00371",
                "source": NARA,
                "verified": True,
                "source_record_id": "NF00371",
            }
        ],
        "source_records": [
            {
                "source_id": NARA,
                "source_type": NARA,
                "source_record_id": "NF00371",
            }
        ],
        "external_hazard": [hazard | {"source_id": NARA}],
        "risk_assessments": [],
        "synthesized_risk": {},
    })
    return store


def test_nara_preview_projects_native_risk_from_verified_source_provenance_without_writing():
    store = _store()

    report = build_nara_risk_inventory(store)

    assert report["mode"] == "read_only_store_preview"
    assert report["storage_write"] is False
    assert report["identity_projection"] is False
    assert report["projection_version"] == "nara-native-risk-v2-source-provenance"
    assert report["migration_gate_passed"] is True
    assert report["latest_source_run_id"] == "run-nara"
    assert report["latest_nara_source_record_count"] == 1
    assert report["unique_latest_nara_source_record_count"] == 1
    assert report["projected_claim_count"] == 1
    assert report["unique_projected_source_record_count"] == 1
    assert report["all_latest_source_records_projected_once"] is True
    assert report["latest_source_records_without_projection"] == 0
    assert report["source_records_with_non_single_claim_count"] == 0
    assert report["canonical_formats_with_nara_assessment"] == 1
    assert report["assessments_missing_source_record_id"] == 0
    assert report["legacy_assessments_missing_source_record_id"] == 0
    assert report["canonical_formats_with_multiple_nara_assessments"] == 0
    assert report["canonical_formats_with_conflicting_nara_levels"] == 0
    assert report["nara_source_records_targeting_multiple_canonicals"] == 0
    assert report["latest_source_records_missing_for_identity_links"] == 0
    assert report["identity_linked_nara_records_without_risk"] == 0
    assert report["canonical_parity_mismatches"] == 0
    assert report["legacy_deduplication_only_mismatches"] == 0
    assert report["canonical_signature_set_parity_mismatches"] == 0
    assert report["canonical_headline_parity_mismatches"] == 0
    assert report["semantic_distribution_matches_legacy"] is True
    assert report["native_label_distribution_matches_legacy"] is True
    assert report["current_persisted_nara_claims"] == 0
    assert report["semantic_levels"] == {"low": 1}
    assert report["native_labels"] == {"Low Risk": 1}
    assert report["native_scales"] == {"nara_file_format_risk_matrix": 1}
    assert report["scope_types"] == {"exact_format": 1}
    claim = report["sample_claims"][0]
    assert claim["source_record_id"] == "NF00371"
    assert claim["source_record_id_basis"] == "verified_canonical_nara_identifier+latest_source_record"
    assert claim["native_score"] == 36.0
    assert claim["semantic_level"] == "low"

    assert store.query("risk_assessment_claims") == []


def test_nara_preview_resolves_merged_conflicting_records_without_guessing_and_keeps_parity():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-nara",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": NARA, "status": "completed"}],
    })
    high = _hazard("High Risk", -33.0, "High", 3.0)
    moderate = _hazard("Moderate Risk", 0.0, "Moderate", 2.0)
    for source_record_id, hazard in (("NF00152", high), ("NF00153", moderate)):
        store.save_source_record({
            "run_id": "run-nara",
            "source_id": NARA,
            "source_type": NARA,
            "source_record_id": source_record_id,
            "name": "dBASE Database",
            "hazard": hazard,
        })

    store.upsert_canonical_format({
        "canonical_id": "puid-x-fmt-8",
        "preferred_name": "dBASE Database",
        "current": True,
        "identifiers": {"nara": ["NF00152", "NF00153"]},
        "identifier_claims": [
            {"kind": "nara", "value": "NF00152", "source": NARA, "verified": True, "source_record_id": "NF00152"},
            {"kind": "nara", "value": "NF00153", "source": NARA, "verified": True, "source_record_id": "NF00153"},
        ],
        "source_records": [
            {"source_id": NARA, "source_type": NARA, "source_record_id": "NF00152"},
            {"source_id": NARA, "source_type": NARA, "source_record_id": "NF00153"},
            {"source_id": NARA, "source_type": NARA, "source_record_id": "NF00999", "relationship": "explicit_puid_cross_reference"},
        ],
        "external_hazard": [
            high | {"source_id": NARA},
            moderate | {"source_id": NARA},
        ],
        "risk_assessments": [],
        "synthesized_risk": {},
    })

    report = build_nara_risk_inventory(store)

    assert report["migration_gate_passed"] is True
    assert report["projected_claim_count"] == 2
    assert report["unique_projected_source_record_count"] == 2
    assert report["assessments_missing_source_record_id"] == 0
    assert report["legacy_assessments_missing_source_record_id"] == 2
    assert report["canonical_formats_with_multiple_nara_assessments"] == 1
    assert report["canonical_formats_with_conflicting_nara_levels"] == 1
    assert report["canonical_parity_mismatches"] == 0
    assert report["canonical_signature_set_parity_mismatches"] == 0
    assert report["canonical_headline_parity_mismatches"] == 0
    assert report["semantic_distribution_matches_legacy"] is True
    assert report["native_label_distribution_matches_legacy"] is True
    assert report["nara_source_records_targeting_multiple_canonicals"] == 0
    assert {item["source_record_id"] for item in report["sample_claims"]} == {"NF00152", "NF00153"}
    assert report["conflicting_level_samples"][0]["semantic_levels"] == ["high", "moderate"]


def test_nara_preview_recovers_source_rows_collapsed_by_legacy_hazard_deduplication():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-nara",
        "finished_at": "2026-08-21T10:00:00Z",
        "sources": [{"source_id": NARA, "status": "completed"}],
    })
    minus14 = _hazard("Moderate Risk", -14.0, "Moderate", 2.0)
    minus16 = _hazard("Moderate Risk", -16.0, "Moderate", 2.0)
    rows = (("NF00166", minus14), ("NF00167", minus14), ("NF00168", minus16))
    for source_record_id, hazard in rows:
        store.save_source_record({
            "run_id": "run-nara",
            "source_id": NARA,
            "source_type": NARA,
            "source_record_id": source_record_id,
            "name": "DVD data file and backup data file",
            "hazard": hazard,
        })

    store.upsert_canonical_format({
        "canonical_id": "puid-x-fmt-419",
        "preferred_name": "DVD data file and backup data file",
        "current": True,
        "identifiers": {"nara": ["NF00166", "NF00167", "NF00168"]},
        "source_records": [
            {"source_id": NARA, "source_type": NARA, "source_record_id": source_id}
            for source_id, _ in rows
        ],
        # Two identical source hazards collapse in the legacy normalized view.
        "external_hazard": [
            minus14 | {"source_id": NARA},
            minus14 | {"source_id": NARA},
            minus16 | {"source_id": NARA},
        ],
        "risk_assessments": [],
        "synthesized_risk": {},
    })

    report = build_nara_risk_inventory(store)

    assert report["migration_gate_passed"] is True
    assert report["latest_nara_source_record_count"] == 3
    assert report["projected_claim_count"] == 3
    assert report["unique_projected_source_record_count"] == 3
    assert report["legacy_projected_claim_count"] == 2
    assert report["canonical_parity_mismatches"] == 1
    assert report["legacy_deduplication_only_mismatches"] == 1
    assert report["canonical_signature_set_parity_mismatches"] == 0
    assert report["canonical_headline_parity_mismatches"] == 0
    assert report["semantic_distribution_matches_legacy"] is False
    assert report["native_label_distribution_matches_legacy"] is False
    assert report["all_latest_source_records_projected_once"] is True


def test_nara_only_config_keeps_puid_authority_with_pronom():
    config = json.loads((ROOT / "config" / "sources.qnl.nara-only.json").read_text(encoding="utf-8"))

    assert config["identifier_kinds"]["puid"]["verified_from"] == [
        "pronom_registry",
        "pronom_droid_xml",
    ]
