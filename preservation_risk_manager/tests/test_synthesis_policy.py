from __future__ import annotations

from preservation_risk_manager.synthesis_policy import load_synthesis_policy, synthesize_assessments


def test_default_policy_prefers_exact_nara_over_broader_dpc_group():
    policy = load_synthesis_policy()
    result = synthesize_assessments([
        {
            "source_id": "nara_digital_preservation_framework",
            "source_type": "nara_digital_preservation_framework",
            "source_label": "NARA",
            "native_label": "Low Risk",
            "scope_type": "exact_format",
            "scope_name": "PDF 1.7",
        },
        {
            "source_id": "dpc_bit_list_2025",
            "source_type": "dpc_bit_list",
            "source_label": "DPC Global Bit List 2025",
            "native_label": "Vulnerable",
            "scope_type": "format_group",
            "scope_name": "PDF",
        },
    ], policy)

    assert result["semantic_level"] == "low"
    assert result["policy_id"] == "qnl-preservation-risk-synthesis"
    assert result["policy_version"] == "1.0"
    assert result["selected_scope_types"] == ["exact_format"]
    assert len(result["contributors"]) == 1
    assert result["contributors"][0]["source_id"] == "nara_digital_preservation_framework"
    assert result["contributors"][0]["semantic_level"] == "low"
    assert len(result["contextual_contributors"]) == 1
    assert result["contextual_contributors"][0]["source_id"] == "dpc_bit_list_2025"
    assert result["contextual_contributors"][0]["semantic_level"] == "moderate"
    assert result["numeric_aggregation"] == "forbidden_across_source_scales"


def test_same_scope_uses_configured_conservative_upper_bound():
    policy = load_synthesis_policy()
    result = synthesize_assessments([
        {
            "source_id": "nara_digital_preservation_framework",
            "native_label": "Low Risk",
            "scope_type": "exact_format",
        },
        {
            "source_id": "new_reviewed_source",
            "semantic_level": "high",
            "scope_type": "exact_format",
        },
    ], policy)

    assert result["semantic_level"] == "high"
    assert result["source_divergence"] is True
    assert result["contributing_levels"] == ["low", "high"]


def test_absent_source_contributes_nothing():
    policy = load_synthesis_policy()
    result = synthesize_assessments([
        {
            "source_id": "nara_digital_preservation_framework",
            "native_label": "Moderate Risk",
            "scope_type": "exact_format",
        }
    ], policy)

    assert result["semantic_level"] == "moderate"
    assert len(result["contributors"]) == 1
    assert result["contextual_contributors"] == []
    assert result["missing_evidence_policy"] == "exclude"
