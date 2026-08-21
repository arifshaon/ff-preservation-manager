import json
from pathlib import Path

from registry_builder.dpc_risk_mapping_mongo import preview_dpc_risk_mapping
from registry_builder.storage.memory import MemoryRegistryStore


ROOT = Path(__file__).resolve().parents[1]


def _mapping():
    return {
        "mapping_version": "dpc-bit-list-2025-v1",
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
                "target_selector": {
                    "identifier_values": {"extension": ["pdf"]},
                    "preferred_name_regex": "(?i)(PDF|Portable Document Format)",
                },
            },
            {
                "rule_id": "dpc-2025-email",
                "status": "contextual_only",
                "source_id": "dpc_bit_list_2025",
                "source_record_id": "N5vlOxZcVm",
            },
        ],
    }


def _dpc_record(run_id: str, label: str, semantic_level: str):
    return {
        "run_id": run_id,
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
                "native_label": label,
                "native_scale": "dpc_global_bit_list_classification",
                "semantic_level": semantic_level,
                "scope_type": "format_group",
                "scope_name": "PDF",
                "native_assessment": {"imminence": 3, "effort": 2},
            }
        ],
    }


def test_store_preview_uses_latest_completed_dpc_run_and_does_not_write():
    store = MemoryRegistryStore()
    store.create_run({
        "run_id": "run-old",
        "finished_at": "2026-01-01T00:00:00+00:00",
        "sources": [{"source_id": "dpc_bit_list_2025", "status": "completed"}],
    })
    store.create_run({
        "run_id": "run-new",
        "finished_at": "2026-08-21T00:00:00+00:00",
        "sources": [{"source_id": "dpc_bit_list_2025", "status": "completed"}],
    })
    store.save_source_record(_dpc_record("run-old", "Endangered", "high"))
    store.save_source_record(_dpc_record("run-new", "Vulnerable", "moderate"))
    store.upsert_canonical_format({
        "canonical_id": "puid-fmt-18",
        "preferred_name": "Portable Document Format 1.4",
        "identifiers": {"extension": ["pdf"], "puid": ["fmt/18"]},
        "risk_assessments": [],
        "synthesized_risk": {},
        "current": True,
    })

    report = preview_dpc_risk_mapping(store, _mapping())

    assert report["mode"] == "read_only_store_preview"
    assert report["storage_write"] is False
    assert report["identity_projection"] is False
    assert report["latest_source_run_id"] == "run-new"
    assert report["dpc_evidence_record_count"] == 1
    assert report["dpc_evidence_only_count"] == 1
    assert report["rules_applied"] == 1
    assert report["rules_skipped"] == 1
    assert report["applied"][0]["target_count"] == 1
    target = report["applied"][0]["targets"][0]
    assert target["canonical_id"] == "puid-fmt-18"
    assert target["mapped_assessments"][0]["native_label"] == "Vulnerable"
    assert target["mapped_assessments"][0]["semantic_level"] == "moderate"
    assert target["mapped_assessments"][0]["native_assessment"] == {"imminence": 3, "effort": 2}
    assert target["projected_synthesized_risk"]["semantic_level"] == "moderate"

    stored = store.get_current_registry_view()[0]
    assert stored.get("risk_assessments") == []
    assert stored.get("synthesized_risk") == {}


def test_dpc_only_config_keeps_puid_authority_with_pronom():
    config = json.loads((ROOT / "config" / "sources.qnl.dpc-only.json").read_text(encoding="utf-8"))

    assert config["identifier_kinds"]["puid"]["verified_from"] == [
        "pronom_registry",
        "pronom_droid_xml",
    ]
    assert config["sources"][0]["id"] == "dpc_bit_list_2025"
    assert config["sources"][0]["type"] == "dpc_bit_list"
