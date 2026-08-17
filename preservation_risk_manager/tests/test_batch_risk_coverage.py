from __future__ import annotations

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.request_api import execute_request


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "coverage_test",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.67,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 1},
                {"band": "Moderate", "min_score": 2, "max_score": 4},
                {"band": "High", "min_score": 5, "max_score": 10}
            ]
        },
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Documented?",
                "critical": True,
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "limited_or_unclear_specification", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True}
                ]
            },
            {
                "id": "q_adoption",
                "label": "Adopted?",
                "evidence_fields": ["sustainability.adoption"],
                "answers": [
                    {"id": "widely_adopted", "points": 0},
                    {"id": "niche_or_declining", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True}
                ]
            }
        ]
    })


def _reader() -> RegistryReader:
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {"canonical_id": "fmt-pdf", "preferred_name": "PDF", "current": True},
            {"canonical_id": "fmt-old-pdf", "preferred_name": "Old PDF", "current": True},
            {"canonical_id": "fmt-unknown-pdf", "preferred_name": "Unknown PDF Variant", "current": True}
        ],
        "criterion_claims": [
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
                "source_id": "a"
            },
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.adoption",
                "value": "high",
                "source_id": "a"
            },
            {
                "canonical_id": "fmt-old-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "limited",
                "source_id": "b"
            },
            {
                "canonical_id": "fmt-old-pdf",
                "criterion_id": "sustainability.adoption",
                "value": "low",
                "source_id": "b"
            }
        ]
    }))


def test_at_risk_query_surfaces_unbanded_candidates_separately():
    result = execute_request(
        _reader(),
        _framework(),
        {
            "action": "list_at_risk_formats",
            "filters": {"family": "PDF", "risk_bands": ["Moderate", "High"]},
            "scope": "global",
            "limit": 100
        }
    )

    assert result["candidate_count"] == 3
    assert result["result_count"] == 1
    assert result["results"][0]["format"]["format_id"] == "fmt-old-pdf"
    assert result["assessment_summary"]["band_counts"] == {
        "High": 1,
        "Moderate": 0,
        "Low": 1,
        "Unbanded": 1
    }
    assert result["unbanded_count"] == 1
    assert result["unbanded_results"][0]["format"]["format_id"] == "fmt-unknown-pdf"
    assert result["unbanded_results"][0]["band_suppressed_reason"] == "not_assessed"
    assert "coverage_warning" in result
