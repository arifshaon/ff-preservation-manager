from __future__ import annotations

import json
from pathlib import Path

from preservation_risk_manager.cli import _compact_answer_document, _criterion_claims_summary, main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_analyze_fixture_cli_outputs_scored_analysis(capsys):
    exit_code = main([
        "analyze-fixture",
        "--framework",
        str(EXAMPLES / "qnl_sustainability.framework.example.json"),
        "--evidence-pack",
        str(EXAMPLES / "pdf.evidence_pack.example.json"),
        "--answers",
        str(EXAMPLES / "pdf.answers.example.json"),
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["format"]["label"] == "Portable Document Format"
    assert result["scope"] == "institution"
    assert result["institution_id"] == "qnl"
    assert result["readiness_status"] == "Covered"
    assert result["exposure_level"] == "High"
    assert result["analysis"]["analysis_status"] == "Assessed"
    assert result["analysis"]["analysed_band"] == "Low"
    assert result["analysis"]["score"] == 0.0
    assert result["local_risk_posture"] == "Low"
    assert len(result["evidence_hash"]) == 64


def test_compact_answer_document_removes_long_source_values():
    compact = _compact_answer_document({
        "derivation": {
            "q_disclosure": {
                "evidence_claims": [
                    {
                        "canonical_id": "loc-fdd000030",
                        "criterion_id": "sustainability.disclosure",
                        "value": "public_specification",
                        "source_id": "loc_fdd_xml",
                        "source_record_id": "fdd000030",
                        "mapping_rule_id": "loc.disclosure.v1",
                        "source_value": "A very long LOC prose field that should not be printed in compact mode.",
                        "rationale": "Also intentionally omitted from compact mode.",
                    }
                ],
                "status": "derived",
            }
        }
    })

    claim = compact["derivation"]["q_disclosure"]["evidence_claims"][0]
    assert claim == {
        "canonical_id": "loc-fdd000030",
        "criterion_id": "sustainability.disclosure",
        "value": "public_specification",
        "source_id": "loc_fdd_xml",
        "source_record_id": "fdd000030",
        "mapping_rule_id": "loc.disclosure.v1",
    }


def test_criterion_claims_summary_groups_by_source_criterion_value_and_institution():
    summary = _criterion_claims_summary([
        {
            "canonical_id": "loc-fdd000030",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd000030",
            "mapping_rule_id": "loc.disclosure.v1",
        },
        {
            "canonical_id": "loc-fdd000030",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "loc_fdd_xml",
            "source_record_id": "fdd000030",
            "mapping_rule_id": "loc.disclosure.v1",
        },
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "qnl_seed",
            "source_record_id": "qnl-evidence-pdf",
            "mapping_rule_id": "qnl.disclosure.v1",
            "institution_id": "qnl",
        },
    ])

    assert summary["total_claims"] == 3
    assert summary["groups"] == [
        {
            "criterion_id": "sustainability.disclosure",
            "source_id": "loc_fdd_xml",
            "value": "public_specification",
            "institution_id": None,
            "canonical_id": "loc-fdd000030",
            "count": 2,
            "source_record_ids": ["fdd000030"],
            "mapping_rule_ids": ["loc.disclosure.v1"],
        },
        {
            "criterion_id": "sustainability.disclosure",
            "source_id": "qnl_seed",
            "value": "public_specification",
            "institution_id": "qnl",
            "canonical_id": "fmt-pdf",
            "count": 1,
            "source_record_ids": ["qnl-evidence-pdf"],
            "mapping_rule_ids": ["qnl.disclosure.v1"],
        },
    ]
