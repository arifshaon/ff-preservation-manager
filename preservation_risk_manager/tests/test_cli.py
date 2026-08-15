from __future__ import annotations

import json
from pathlib import Path

from preservation_risk_manager.cli import main


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
