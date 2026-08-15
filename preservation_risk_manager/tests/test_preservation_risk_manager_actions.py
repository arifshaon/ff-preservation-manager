from __future__ import annotations

from preservation_risk_manager.actions import resolve_action_policies


ACTION_DEFINITIONS = [
    {
        "action_id": "preserve_as_is",
        "conflicts_with": ["migrate_to_preferred_format", "normalize_on_ingest"],
        "compatible_with": ["escalate_specialist_review", "monitor"],
    },
    {
        "action_id": "migrate_to_preferred_format",
        "conflicts_with": ["preserve_as_is"],
    },
    {"action_id": "preserve_with_monitoring"},
    {"action_id": "escalate_specialist_review"},
    {"action_id": "develop_local_handling_profile"},
]


def _netcdf_policies():
    return [
        {
            "policy_id": "high-risk-default",
            "specificity": 0,
            "mode": "replace",
            "actions": [{"action_id": "preserve_with_monitoring"}],
        },
        {
            "policy_id": "qnl-no-expertise-policy",
            "specificity": 2,
            "mode": "supplement",
            "actions": [
                {"action_id": "escalate_specialist_review"},
                {"action_id": "develop_local_handling_profile"},
            ],
        },
        {
            "policy_id": "qnl-netcdf-action-override",
            "specificity": 4,
            "mode": "replace",
            "actions": [{"action_id": "migrate_to_preferred_format"}],
        },
    ]


def test_action_resolution_is_deterministic_regardless_of_policy_insertion_order():
    forward = resolve_action_policies(_netcdf_policies(), action_definitions=ACTION_DEFINITIONS)
    reverse = resolve_action_policies(list(reversed(_netcdf_policies())), action_definitions=ACTION_DEFINITIONS)

    assert forward == reverse
    assert forward["recommendation_status"] == "ok"


def test_replace_and_supplement_are_orthogonal_for_netcdf_example():
    result = resolve_action_policies(_netcdf_policies(), action_definitions=ACTION_DEFINITIONS)

    assert result["applied"] == ["qnl-no-expertise-policy", "qnl-netcdf-action-override"]
    assert result["suppressed"] == [
        {
            "policy_id": "high-risk-default",
            "reason": "lower-specificity replace suppressed by qnl-netcdf-action-override",
        }
    ]
    assert [action["action_id"] for action in result["final_actions"]] == [
        "escalate_specialist_review",
        "develop_local_handling_profile",
        "migrate_to_preferred_format",
    ]


def test_same_specificity_double_replace_is_configuration_error():
    result = resolve_action_policies(
        [
            {
                "policy_id": "policy-a",
                "specificity": 3,
                "mode": "replace",
                "actions": [{"action_id": "preserve_as_is"}],
            },
            {
                "policy_id": "policy-b",
                "specificity": 3,
                "mode": "replace",
                "actions": [{"action_id": "preserve_with_monitoring"}],
            },
        ],
        action_definitions=ACTION_DEFINITIONS,
    )

    assert result["recommendation_status"] == "configuration_error"
    assert result["configuration_errors"][0]["type"] == "same_specificity_replace_conflict"
    assert result["final_actions"] == []


def test_conflicting_actions_are_configuration_error_not_merged_recommendation():
    result = resolve_action_policies(
        [
            {
                "policy_id": "low-risk-default",
                "specificity": 0,
                "mode": "replace",
                "actions": [{"action_id": "preserve_as_is"}],
            },
            {
                "policy_id": "format-migration-override",
                "specificity": 4,
                "mode": "supplement",
                "actions": [{"action_id": "migrate_to_preferred_format"}],
            },
        ],
        action_definitions=ACTION_DEFINITIONS,
    )

    assert result["recommendation_status"] == "configuration_error"
    assert result["configuration_errors"][0]["type"] == "conflicting_actions"
    assert result["final_actions"] == []
    assert [action["action_id"] for action in result["candidate_actions"]] == [
        "preserve_as_is",
        "migrate_to_preferred_format",
    ]
