from __future__ import annotations

from copy import deepcopy

from preservation_risk_manager.synthesis_policy import (
    SynthesisPolicy,
    load_synthesis_policy,
    map_risk_term,
    synthesize_assessments,
)


def _default_policy_dict():
    return deepcopy(load_synthesis_policy().raw)


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


def test_policy_can_change_scope_and_aggregation_without_code_changes():
    data = _default_policy_dict()
    data["synthesis"] = {
        **data["synthesis"],
        "scope_selection": "all_mapped_assessments",
        "broader_scope_policy": "context_only",
        "same_scope_aggregation": "lowest_semantic_concern",
    }
    policy = SynthesisPolicy.from_dict(data)

    result = synthesize_assessments([
        {
            "source_id": "nara_digital_preservation_framework",
            "native_label": "High Risk",
            "scope_type": "exact_format",
        },
        {
            "source_type": "dpc_bit_list",
            "native_label": "Vulnerable",
            "scope_type": "format_group",
        },
    ], policy)

    assert result["scope_selection"] == "all_mapped_assessments"
    assert result["same_scope_aggregation"] == "lowest_semantic_concern"
    assert result["semantic_level"] == "moderate"
    assert len(result["contributors"]) == 2
    assert result["contextual_contributors"] == []


def test_majority_aggregation_tie_break_is_configurable():
    data = _default_policy_dict()
    data["synthesis"] = {
        **data["synthesis"],
        "scope_selection": "all_mapped_assessments",
        "same_scope_aggregation": {
            "operator": "majority_semantic_level",
            "tie_break": "lowest_semantic_concern",
        },
    }
    policy = SynthesisPolicy.from_dict(data)

    result = synthesize_assessments([
        {"source_id": "x", "semantic_level": "low", "scope_type": "exact_format"},
        {"source_id": "y", "semantic_level": "high", "scope_type": "format_group"},
    ], policy)

    assert result["semantic_level"] == "low"
    assert result["same_scope_aggregation"] == "majority_semantic_level"


def test_source_native_risk_terminology_maps_only_through_configured_rule():
    policy = load_synthesis_policy()

    dpc = map_risk_term(
        "Vulnerable",
        policy,
        source_context={"source_type": "dpc_bit_list"},
    )
    unknown = map_risk_term(
        "Needs watching",
        policy,
        source_context={"source_type": "dpc_bit_list"},
    )

    assert dpc["mapped"] is True
    assert dpc["semantic_level"] == "moderate"
    assert dpc["rule_id"] == "dpc-global-bit-list"
    assert unknown["mapped"] is False
    assert unknown["semantic_level"] is None


def test_ai_policy_is_capability_driven_and_keeps_governed_result_as_baseline():
    policy = load_synthesis_policy()
    ai = policy.ai

    assert ai["version"] == "2.0"
    assert ai["strategy"] == "capability_driven_contextual_synthesis"
    assert ai["external_capabilities_policy"] == "make_provider_capabilities_available_and_let_model_decide"
    assert ai["configured_source_mappings"] == "supply_as_methodology_context_not_binding_on_ai_result"
    assert ai["consumer_decision_policy"] == "return_ai_result_alongside_governed_baseline"
    assert ai["automatic_persistence"] is False
