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
            {"band": "High", "min_score": 13, "max_score": 30},
        ],
    },
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


def _write_framework(tmp_path):
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK), encoding="utf-8")
    return framework_path


def _write_registry(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({
            "canonical_formats": [
                {
                    "canonical_id": "fmt-pdf",
                    "preferred_name": "PDF",
                    "identifiers": {
                        "puid": ["fmt/18"],
                        "extension": ["pdf"],
                        "mime": ["application/pdf"],
                    },
                }
            ],
            "criterion_claims": [
                {
                    "canonical_id": "fmt-pdf",
                    "criterion_id": "sustainability.disclosure",
                    "value": "public_specification",
                    "source_id": "qnl_seed",
                    "source_record_id": "qnl-evidence-pdf",
                    "mapping_rule_id": "qnl.disclosure.v1",
                    "institution_id": "qnl",
                    "source_independence": "institution_scoped",
                    "review_status": "approved",
                    "directness": "explicit",
                    "covers": "partial",
                },
                {
                    "canonical_id": "fmt-pdf",
                    "criterion_id": "sustainability.adoption",
                    "value": "high",
                    "source_id": "qnl_seed",
                    "source_record_id": "qnl-evidence-pdf",
                    "mapping_rule_id": "qnl.adoption.v1",
                    "institution_id": "qnl",
                    "source_independence": "institution_scoped",
                    "review_status": "approved",
                    "directness": "explicit",
                    "covers": "partial",
                },
                {
                    "canonical_id": "fmt-pdf",
                    "criterion_id": "sustainability.external_dependencies",
                    "value": "low",
                    "source_id": "qnl_seed",
                    "source_record_id": "qnl-evidence-pdf",
                    "mapping_rule_id": "qnl.external_dependencies.v1",
                    "institution_id": "qnl",
                    "source_independence": "institution_scoped",
                    "review_status": "approved",
                    "directness": "explicit",
                    "covers": "partial",
                },
            ],
        }),
        encoding="utf-8",
    )
    return registry_path


def test_propose_policy_change_builds_draft_without_writing(tmp_path, capsys):
    framework_path = _write_framework(tmp_path)
    registry_path = _write_registry(tmp_path)

    rc = main([
        "propose-policy-change",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--format", "fmt-pdf",
        "--institution", "qnl",
        "--readiness-status", "Covered",
        "--exposure-level", "High",
        "--goal", "Recommend whether QNL should monitor, migrate, or take no action.",
        "--compact-evidence",
    ])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "draft"
    assert output["proposal_type"] == "policy_change"
    assert output["llm_execution"] == "not_invoked"
    assert output["write_status"] == "not_written"
    assert output["approval_required"] is True
    assert output["affected_formats"] == [{"canonical_id": "fmt-pdf", "preferred_name": "PDF"}]
    assert output["analysis_context"]["analysis"]["analysed_band"] == "Low"
    assert output["analysis_context"]["local_risk_posture"] == "Low"
    assert output["analysis_context"]["criterion_claims_summary"]["total_claims"] == 3

    policy_record = output["proposed_policy_record"]
    assert policy_record["review_status"] == "draft"
    assert policy_record["scope"] == "institution"
    assert policy_record["institution_id"] == "qnl"
    assert policy_record["target"] == {"canonical_id": "fmt-pdf", "preferred_name": "PDF"}
    assert policy_record["actions"][0]["action_id"] == "take_no_action_now"
    assert policy_record["approval"] == {
        "approved_by": None,
        "effective_from": None,
        "supersedes": None,
        "review_status": "draft",
    }
    assert output["proposed_diff"] == [
        {
            "op": "add",
            "path": "/policy_records/-",
            "value": policy_record,
        }
    ]
    assert output["llm_prompt"]["user"]["context"]["analysis"]["analysed_band"] == "Low"
    assert "Do not invent evidence." in output["llm_prompt"]["user"]["constraints"]
