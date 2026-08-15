from pathlib import Path
import json

from registry_builder.pipeline import run_pipeline


def test_pipeline_can_apply_criterion_mapping_in_memory(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = {
        "pipeline_version": "0.1.0",
        "incremental_source_updates": True,
        "storage": {"type": "memory"},
        "exports": {"enabled": True},
        "method_profiles": {"enabled": False},
        "criterion_mapping": {
            "enabled": True,
            "mode": "apply",
            "criteria": str(repo_root / "config" / "criteria" / "v1.json"),
            "mappings": str(repo_root / "config" / "criterion_mappings" / "qnl_institution_format_evidence.v1.json"),
            "include_drafts": False,
            "scope": "all",
        },
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

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "out")

    assert report["criterion_mapping"]["enabled"] is True
    assert report["criterion_mapping"]["claims_generated"] > 0
    assert "sustainability.disclosure" in report["criterion_mapping"]["claims_by_criterion"]
    exported_claims = tmp_path / "out" / "criterion_claims.json"
    assert exported_claims.exists()
    claims = json.loads(exported_claims.read_text(encoding="utf-8"))
    assert all("confidence" not in claim for claim in claims)
    assert any(claim["criterion_id"] == "sustainability.disclosure" for claim in claims)


def test_pipeline_leaves_criterion_mapping_disabled_by_default(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = {
        "pipeline_version": "0.1.0",
        "storage": {"type": "memory"},
        "exports": {"enabled": False},
        "method_profiles": {"enabled": False},
        "identifier_kinds": {
            "puid": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "loc": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
        },
        "sources": [
            {
                "id": "qnl_institution_format_evidence_2026_seed",
                "type": "qnl_institution_format_evidence",
                "enabled": True,
                "required": True,
                "uris": [str(repo_root / "examples" / "qnl_institution_format_evidence.seed.json")],
            }
        ],
    }
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "out")

    assert report["criterion_mapping"] == {"enabled": False, "claims_generated": 0}
