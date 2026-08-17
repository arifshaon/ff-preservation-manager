from __future__ import annotations

import json

from preservation_risk_manager import integration_cli
from preservation_risk_manager.human_renderer import render_human_response


def _question_response() -> dict:
    return {
        "status": "ok",
        "request": {
            "action": "assess_format_questions",
            "format": "PDF",
            "filters": {
                "family": None,
                "risk_bands": [],
                "domains": ["software_dependencies_environment"],
                "question_ids": [],
                "content_type": None,
            },
            "scope": "global",
            "institution_id": None,
            "limit": 100,
        },
        "result": {
            "format": {"format_id": "fmt-pdf", "label": "PDF"},
            "selected_question_count": 2,
            "answered_question_count": 1,
            "evidence_completeness": 0.5,
            "questions": [
                {
                    "question_id": "q_rendering_environment",
                    "label": "Is rendering dependent on specific operating systems, proprietary software, or legacy hardware?",
                    "domain_id": "software_dependencies_environment",
                    "domain_label": "Software Dependencies & Environment",
                    "guidance": "Assess runtime and software dependencies.",
                    "evidence_fields": ["software.rendering_dependencies"],
                    "answer_id": "low_risk",
                    "answer_label": "Common cross-platform tooling is available",
                    "derivation_status": "derived",
                    "abstention": False,
                    "evidence": [
                        {
                            "source_id": "loc",
                            "source_record_id": "fdd000030",
                            "criterion_id": "software.rendering_dependencies",
                            "value": "common_tooling",
                        }
                    ],
                },
                {
                    "question_id": "q_external_assets",
                    "label": "Does the format rely on external assets?",
                    "domain_id": "software_dependencies_environment",
                    "domain_label": "Software Dependencies & Environment",
                    "guidance": "Check for unembedded or externally referenced resources.",
                    "evidence_fields": ["sustainability.external_dependencies"],
                    "answer_id": "unknown",
                    "answer_label": "Evidence is unavailable or insufficient",
                    "derivation_status": "missing_evidence",
                    "abstention": True,
                    "evidence": [],
                },
            ],
            "overall_framework_assessment": {
                "risk_band": None,
                "band_suppressed_reason": "framework_banding_disabled",
                "analysis_status": "Partially Assessed",
                "score": 0,
                "max_score": 44,
                "calibration_status": "draft_unvalidated",
                "banding_enabled": False,
            },
        },
    }


def test_human_renderer_provides_detailed_evidence_aware_answer():
    text = render_human_response(_question_response())

    assert "PDF preservation-risk assessment" in text
    assert "Evidence coverage: 1 of 2 selected questions answered (50%)." in text
    assert "draft_unvalidated" in text
    assert "Software Dependencies & Environment" in text
    assert "Common cross-platform tooling is available" in text
    assert "loc / fdd000030 / software.rendering_dependencies / value=common_tooling" in text
    assert "Unknown / insufficient evidence" in text
    assert "sustainability.external_dependencies" in text
    assert "This is a partial assessment" in text


def test_ask_defaults_to_human_text(monkeypatch, capsys):
    monkeypatch.setattr(integration_cli, "_ask", lambda args: _question_response())

    code = integration_cli.main([
        "ask",
        "What are the software dependency risks of PDF?",
        "--framework", "dummy-framework.json",
        "--registry-json", "dummy-registry.json",
        "--ai-config", "dummy-ai.json",
    ])

    output = capsys.readouterr().out
    assert code == 0
    assert output.startswith("PDF preservation-risk assessment")
    assert not output.lstrip().startswith("{")


def test_ask_json_flag_returns_canonical_json(monkeypatch, capsys):
    monkeypatch.setattr(integration_cli, "_ask", lambda args: _question_response())

    code = integration_cli.main([
        "ask",
        "What are the software dependency risks of PDF?",
        "--framework", "dummy-framework.json",
        "--registry-json", "dummy-registry.json",
        "--ai-config", "dummy-ai.json",
        "--json",
    ])

    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert code == 0
    assert parsed["request"]["action"] == "assess_format_questions"


def test_query_json_remains_machine_readable(monkeypatch, capsys):
    machine_response = {
        "status": "ok",
        "request": {"action": "assess_format_questions"},
        "result": {"format": {"format_id": "fmt-pdf", "label": "PDF"}},
    }
    monkeypatch.setattr(integration_cli, "_query_json", lambda args: machine_response)

    code = integration_cli.main([
        "query-json",
        "--framework", "dummy-framework.json",
        "--registry-json", "dummy-registry.json",
        "--request-json", "{}",
    ])

    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert code == 0
    assert parsed == machine_response
