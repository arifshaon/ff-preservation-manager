from preservation_risk_manager.synthesis_policy import SynthesisPolicy, map_risk_term, synthesize_assessments


def test_synthesis_engine_does_not_depend_on_qnl_risk_level_names():
    policy = SynthesisPolicy.from_dict({
        "policy_id": "custom-test",
        "version": "1",
        "semantic_levels": [
            {"id": "green", "label": "Routine", "rank": 10},
            {"id": "amber", "label": "Watch", "rank": 20},
            {"id": "red", "label": "Intervene", "rank": 30},
        ],
        "source_rules": [
            {
                "rule_id": "custom-source",
                "source_match": {"source_id": "custom"},
                "role": "headline_risk",
                "value_fields": ["native_label"],
                "value_map": {"routine": "green", "watch": "amber", "intervention required": "red"},
                "accept_existing_semantic_level": False,
                "default_scope": "exact_format",
            }
        ],
        "evidence_source_roles": [],
        "synthesis": {
            "headline_roles": ["headline_risk"],
            "missing_assessment_policy": "exclude",
            "scope_precedence": [["exact_format"], ["format_group"]],
            "scope_selection": "most_specific_available",
            "same_scope_aggregation": "highest_semantic_concern",
            "broader_scope_policy": "context_only",
            "numeric_aggregation": "forbidden_across_source_scales",
        },
        "ai": {},
    })

    mapping = map_risk_term("Watch", policy, source_context={"source_id": "custom"})
    result = synthesize_assessments([
        {"source_id": "custom", "native_label": "Routine", "scope_type": "exact_format"},
        {"source_id": "custom", "native_label": "Watch", "scope_type": "exact_format"},
    ], policy)

    assert mapping["semantic_level"] == "amber"
    assert mapping["semantic_label"] == "Watch"
    assert result["semantic_level"] == "amber"
    assert result["semantic_label"] == "Watch"
    assert result["headline_roles"] == ["headline_risk"]
