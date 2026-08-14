from __future__ import annotations

import json

from registry_builder.pipeline import run_pipeline


def test_pipeline_persists_to_file_store_without_exports(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_record_id": "pdf-a",
                        "name": "PDF/A",
                        "extensions": ["pdf"],
                        "hazard": {"band": "Low", "rating": 1.0},
                        "institution_policy": {
                            "institution_id": "qnl",
                            "institution_format_id": "QNL-PDFA",
                            "local_risk_level": "Low Risk",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store_path = tmp_path / "registry_store"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage": {"type": "file", "path": str(store_path)},
                "exports": {"enabled": False},
                "method_profiles": {"enabled": False},
                "sources": [
                    {
                        "id": "test_source",
                        "type": "standard_json",
                        "enabled": True,
                        "uris": [str(source_path)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "output")

    assert report["storage"]["type"] == "file"
    assert report["exports_enabled"] is False
    assert report["canonical_formats"] == 1
    assert len(list((store_path / "runs").glob("*.json"))) == 1
    assert len(list((store_path / "source_snapshots").glob("*.json"))) == 1
    assert len(list((store_path / "source_records").glob("*.json"))) == 1
    assert len(list((store_path / "canonical_formats").glob("*.json"))) == 1
    assert len(list((store_path / "institution_policy_overlays").glob("*.json"))) == 1
    assert len(list((store_path / "hazard_assessments").glob("*.json"))) == 1
    assert not (tmp_path / "output" / "registry.json").exists()
