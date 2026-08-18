import json
from pathlib import Path

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.request_api import execute_request


ROOT = Path(__file__).resolve().parents[1]


def _framework() -> RiskFramework:
    return RiskFramework.from_dict(
        json.loads((ROOT / "examples" / "qnl_sustainability.framework.example.json").read_text(encoding="utf-8"))
    )


def test_example_framework_bands_two_of_three_answers_and_does_not_report_unknown_as_risk():
    store = JsonRegistryStore({
        "canonical_formats": [{
            "canonical_id": "puid-fmt-14",
            "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
            "identifiers": {"puid": ["fmt/14"]},
            "current": True,
        }],
        "criterion_claims": [
            {
                "canonical_id": "puid-fmt-14",
                "criterion_id": "sustainability.disclosure",
                "value": "undocumented",
                "source_id": "pronom_registry",
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-14",
                "criterion_id": "technical.hardware_dependency",
                "value": "none",
                "source_id": "nara_digital_preservation_framework",
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-14",
                "criterion_id": "technical.plugin_script_dependency",
                "value": "none",
                "source_id": "nara_digital_preservation_framework",
                "current": True,
            },
        ],
    })

    result = execute_request(
        RegistryReader(store=store),
        _framework(),
        {"action": "assess_format", "format": "fmt/14", "scope": "global"},
    )["result"]

    assert result["analysis_status"] == "Partially Assessed"
    assert result["evidence_completeness"] == 2 / 3
    assert result["risk_band"] == "Low"
    assert result["band_suppressed_reason"] is None
    assert result["missing_count"] == 1
    assert result["abstention_count"] == 1
    assert result["main_risk_factors"] == [{
        "question_id": "q_disclosure",
        "answer_id": "limited_or_unclear_specification",
        "weighted_points": 3.0,
        "derivation_status": "derived",
    }]
