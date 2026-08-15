from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    label: str | None = None
    conflicts_with: tuple[str, ...] = ()
    compatible_with: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionDefinition":
        return cls(
            action_id=str(data["action_id"]),
            label=data.get("label"),
            conflicts_with=tuple(data.get("conflicts_with") or ()),
            compatible_with=tuple(data.get("compatible_with") or ()),
        )


@dataclass(frozen=True)
class MatchedPolicy:
    policy_id: str
    specificity: int
    mode: str
    actions: tuple[dict[str, Any], ...] = ()
    suppresses: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchedPolicy":
        mode = str(data.get("mode") or data.get("override_mode") or "supplement")
        if mode not in {"replace", "supplement"}:
            raise ValueError(f"Unsupported policy mode: {mode}")
        return cls(
            policy_id=str(data["policy_id"]),
            specificity=int(data.get("specificity", 0)),
            mode=mode,
            actions=tuple(dict(action) for action in data.get("actions", [])),
            suppresses=tuple(str(x) for x in data.get("suppresses", [])),
        )


def _policy_summary(policy: MatchedPolicy) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "specificity": policy.specificity,
        "mode": policy.mode,
    }


def _action_id(action: dict[str, Any]) -> str:
    return str(action.get("action_id") or "")


def _configuration_error(error_type: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"type": error_type, "message": message, **extra}


def _same_specificity_replace_errors(policies: list[MatchedPolicy]) -> list[dict[str, Any]]:
    by_specificity: dict[int, list[MatchedPolicy]] = {}
    for policy in policies:
        if policy.mode == "replace":
            by_specificity.setdefault(policy.specificity, []).append(policy)
    errors = []
    for specificity, items in sorted(by_specificity.items()):
        if len(items) <= 1:
            continue
        errors.append(_configuration_error(
            "same_specificity_replace_conflict",
            "Multiple replace policies matched at the same specificity.",
            specificity=specificity,
            policies=sorted(policy.policy_id for policy in items),
        ))
    return errors


def _conflicting_action_errors(
    actions: list[dict[str, Any]],
    action_definitions: dict[str, ActionDefinition],
) -> list[dict[str, Any]]:
    action_ids = [_action_id(action) for action in actions if _action_id(action)]
    errors: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for action_id in action_ids:
        definition = action_definitions.get(action_id)
        if not definition:
            continue
        for conflict in definition.conflicts_with:
            if conflict not in action_ids:
                continue
            pair = tuple(sorted((action_id, conflict)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            errors.append(_configuration_error(
                "conflicting_actions",
                "Conflicting actions were produced by applied policies.",
                actions=list(pair),
            ))
    return errors


def resolve_action_policies(
    matched_policies: list[dict[str, Any]] | list[MatchedPolicy],
    *,
    action_definitions: list[dict[str, Any]] | list[ActionDefinition] | None = None,
) -> dict[str, Any]:
    """Resolve matched action policies deterministically.

    Policy semantics:
    - higher-specificity replace policies suppress lower-specificity replace policies;
    - supplement policies apply across specificity levels;
    - policies can explicitly suppress policies by ID;
    - two replace policies at the same specificity are a configuration error;
    - incompatible final actions are a configuration error, not a merged result.
    """
    policies = [p if isinstance(p, MatchedPolicy) else MatchedPolicy.from_dict(p) for p in matched_policies]
    policies = sorted(policies, key=lambda p: (p.specificity, p.mode, p.policy_id))
    definitions = {
        (d.action_id if isinstance(d, ActionDefinition) else str(d["action_id"])): (
            d if isinstance(d, ActionDefinition) else ActionDefinition.from_dict(d)
        )
        for d in (action_definitions or [])
    }

    errors = _same_specificity_replace_errors(policies)
    explicit_suppressed_ids = {
        suppressed
        for policy in policies
        for suppressed in policy.suppresses
    }

    replace_policies = [policy for policy in policies if policy.mode == "replace"]
    selected_replace = replace_policies[-1] if replace_policies else None

    applied: list[MatchedPolicy] = []
    suppressed: list[dict[str, Any]] = []
    for policy in policies:
        if policy.policy_id in explicit_suppressed_ids:
            suppressed.append({
                "policy_id": policy.policy_id,
                "reason": "explicitly suppressed by another matched policy",
            })
            continue
        if policy.mode == "replace":
            if selected_replace and policy.policy_id == selected_replace.policy_id:
                applied.append(policy)
            else:
                suppressed.append({
                    "policy_id": policy.policy_id,
                    "reason": f"lower-specificity replace suppressed by {selected_replace.policy_id if selected_replace else 'selected replace policy'}",
                })
            continue
        applied.append(policy)

    candidate_actions: list[dict[str, Any]] = []
    seen_action_ids: set[str] = set()
    for policy in applied:
        for action in policy.actions:
            action_id = _action_id(action)
            if not action_id or action_id in seen_action_ids:
                continue
            seen_action_ids.add(action_id)
            candidate_actions.append(dict(action))

    errors.extend(_conflicting_action_errors(candidate_actions, definitions))
    recommendation_status = "configuration_error" if errors else "ok"
    return {
        "recommendation_status": recommendation_status,
        "matched": [_policy_summary(policy) for policy in policies],
        "applied": [policy.policy_id for policy in sorted(applied, key=lambda p: (p.specificity, p.policy_id))],
        "suppressed": suppressed,
        "configuration_errors": errors,
        "candidate_actions": candidate_actions,
        "final_actions": [] if errors else candidate_actions,
    }
