import json

import pytest

from preservation_risk_manager import data_access
from preservation_risk_manager.cli import main


FRAMEWORK = {
    "framework_id": "example",
    "version": "1",
    "unknown_answer_id": "unknown",
    "score_bands": [
        {"band": "Low", "min_score": 0, "max_score": 5},
        {"band": "Moderate", "min_score": 6, "max_score": 12},
        {"band": "High", "min_score": 13, "max_score": 30},
    ],
    "questions": [
        {
            "id": "q_disclosure",
            "evidence_fields": ["sustainability.disclosure"],
            "critical": True,
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_or_unclear_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_adoption",
            "evidence_fields": ["sustainability.adoption"],
            "answers": [
                {"id": "widely_adopted", "points": 0},
                {"id": "niche_or_declining", "points": 4},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_external_dependencies",
            "evidence_fields": ["sustainability.external_dependencies"],
            "weight": 2,
            "answers": [
                {"id": "no_special_dependency", "points": 0},
                {"id": "specialist_dependency", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
    ],
}


class FakeStore:
    def __init__(self, collections):
        self.collections = collections

    def query(self, collection, filt=None):
        filt = filt or {}
        return [
            row
            for row in self.collections.get(collection, [])
            if all(row.get(key) == value for key, value in filt.items())
        ]


def _write_framework(tmp_path):
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK), encoding="utf-8")
    return framework_path


def _pdf_record():
    return {
        "canonical_id": "puid-fmt-18",
        "preferred_name": "Portable Document Format",
        "identifiers": {
            "puid": ["fmt/18"],
            "extension": ["pdf"],
            "mime": ["application/pdf"],
        },
        "evidence_claims": [
            {"claim_id": "a", "criterion_id": "sustainability.disclosure", "value": "openly_documented"},
            {"claim_id": "b", "criterion_id": "sustainability.adoption", "value": "widely_adopted"},
            {"claim_id": "c", "criterion_id": "sustainability.external_dependencies", "value": "none"},
        ],
    }


def test_analyze_format_resolves_registry_json_and_derives_answers(tmp_path, capsys):
    framework_path = _write_framework(tmp_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([_pdf_record()]), encoding="utf-8")

    rc = main([
        "analyze-format",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--format", "fmt/18",
        "--institution", "qnl",
        "--readiness-status", "Covered",
        "--exposure-level", "High",
    ])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["resolution"]["status"] == "resolved"
    assert output["resolution"]["match_type"] == "authority_identifier"
    assert output["format"]["format_id"] == "puid-fmt-18"
    assert output["format"]["puids"] == ["fmt/18"]
    assert output["analysis"]["analysed_band"] == "Low"
    assert output["analysis"]["analysis_status"] == "Assessed"
    assert output["local_risk_posture"] == "Low"
    assert output["derived_answers"]["answers"]["q_disclosure"] == "public_specification"


def test_analyze_format_can_read_registry_builder_storage_config(tmp_path, monkeypatch, capsys):
    framework_path = _write_framework(tmp_path)
    storage_config_path = tmp_path / "registry-builder-config.json"
    storage_config_path.write_text(
        json.dumps({
            "storage": {"type": "file", "path": "registry_store"},
            "sources": [],
        }),
        encoding="utf-8",
    )
    created = []

    def fake_create_store(config):
        created.append(config)
        return FakeStore({"canonical_formats": [_pdf_record()]})

    monkeypatch.setattr(data_access, "create_store_from_registry_builder", fake_create_store)

    rc = main([
        "analyze-format",
        "--framework", str(framework_path),
        "--storage-config", str(storage_config_path),
        "--format", "fmt/18",
        "--institution", "qnl",
        "--readiness-status", "Covered",
    ])

    assert rc == 0
    assert created == [{"type": "file", "path": "registry_store"}]
    output = json.loads(capsys.readouterr().out)
    assert output["resolution"]["status"] == "resolved"
    assert output["analysis"]["analysis_status"] == "Assessed"
    assert output["local_risk_posture"] == "Low"


def test_analyze_format_keeps_missing_evidence_as_needs_assessment(tmp_path, capsys):
    framework_path = _write_framework(tmp_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps([
            {
                "canonical_id": "fmt-empty",
                "preferred_name": "Empty Evidence Format",
                "identifiers": {"extension": ["empty"]},
            }
        ]),
        encoding="utf-8",
    )

    rc = main([
        "analyze-format",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--format", "empty",
        "--institution", "qnl",
    ])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["analysis"]["analysis_status"] == "Not Assessed"
    assert output["analysis"]["analysed_band"] is None
    assert output["local_risk_posture"] == "Needs Assessment"
    assert output["derived_answers"]["derivation"]["q_disclosure"]["status"] == "missing_evidence"


def test_analyze_format_reports_missing_registry_json_without_traceback(tmp_path, capsys):
    framework_path = _write_framework(tmp_path)
    missing_registry = tmp_path / "missing-registry.json"

    with pytest.raises(SystemExit) as exc:
        main([
            "analyze-format",
            "--framework", str(framework_path),
            "--registry-json", str(missing_registry),
            "--format", "fmt/18",
        ])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Registry JSON file not found" in captured.err
    assert "Traceback" not in captured.err
