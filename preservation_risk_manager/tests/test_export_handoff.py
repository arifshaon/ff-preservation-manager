import json

from preservation_risk_manager.cli import main


FRAMEWORK = {
    "framework_id": "example",
    "version": "1",
    "unknown_answer_id": "unknown",
    "scale": {
        "direction": "higher_is_risk",
        "min_completeness_for_band": 0.67,
        "bands": [
            {"band": "Low", "min_score": 0, "max_score": 5},
            {"band": "Moderate", "min_score": 6, "max_score": 12},
            {"band": "High", "min_score": 13, "max_score": 30}
        ]
    },
    "questions": [
        {
            "id": "q_disclosure",
            "evidence_fields": ["sustainability.disclosure"],
            "critical": True,
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_or_unclear_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True}
            ]
        },
        {
            "id": "q_adoption",
            "evidence_fields": ["sustainability.adoption"],
            "answers": [
                {"id": "widely_adopted", "points": 0},
                {"id": "niche_or_declining", "points": 4},
                {"id": "unknown", "points": 1, "abstention": True}
            ]
        },
        {
            "id": "q_external_dependencies",
            "evidence_fields": ["sustainability.external_dependencies"],
            "weight": 2,
            "answers": [
                {"id": "no_special_dependency", "points": 0},
                {"id": "specialist_dependency", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True}
            ]
        }
    ]
}


def test_analyze_format_uses_sibling_criterion_claims_export(tmp_path, capsys):
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK), encoding="utf-8")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps([
            {
                "canonical_id": "fmt-pdf",
                "preferred_name": "PDF",
                "identifiers": {"puid": ["fmt/18"]}
            }
        ]),
        encoding="utf-8",
    )

    claims = [
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "loc.disclosure.v1"
        },
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.adoption",
            "value": "high",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "loc.adoption.v1"
        },
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.external_dependencies",
            "value": "none",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "loc.dependencies.v1"
        }
    ]
    (tmp_path / "criterion_claims.jsonl").write_text(
        "\n".join(json.dumps(row) for row in claims) + "\n",
        encoding="utf-8",
    )

    rc = main([
        "analyze-format",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--format", "fmt-pdf"
    ])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["criterion_claims_used"] == 3
    assert output["analysis"]["analysis_status"] == "Assessed"
    assert output["analysis"]["analysed_band"] == "Low"
    assert output["analysis"]["evidence_completeness"] == 1.0
