from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Callable, Iterable


DEFAULT_SYNTHESIS_POLICY_PATH = (
    Path(__file__).resolve().parent
    / "config"
    / "qnl_preservation_risk_synthesis.v1.json"
)


class SynthesisPolicyError(ValueError):
    """Raised when a preservation-risk synthesis policy is invalid."""


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _operator_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("operator") or value.get("name")
    return str(value or "").strip()


def _operator_options(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if key not in {"operator", "name"}}


@dataclass(frozen=True)
class SemanticLevel:
    id: str
    label: str
    rank: int


@dataclass(frozen=True)
class SourceRule:
    rule_id: str
    source_match: dict[str, str]
    role: str
    value_fields: tuple[str, ...]
    value_map: dict[str, str]
    accept_existing_semantic_level: bool
    default_scope: str | None

    def matches(self, assessment: dict[str, Any]) -> bool:
        if not self.source_match:
            return True
        for key, expected in self.source_match.items():
            if _norm(assessment.get(key)) != _norm(expected):
                return False
        return True


ScopeSelector = Callable[[list[dict[str, Any]], "SynthesisPolicy", dict[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]], int | None]]
BroaderScopeOperator = Callable[[list[dict[str, Any]], list[dict[str, Any]], "SynthesisPolicy", dict[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]]]]
Aggregator = Callable[[list[dict[str, Any]], "SynthesisPolicy", dict[str, Any]], dict[str, Any]]
MissingOperator = Callable[[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]
NumericOperator = Callable[[list[dict[str, Any]], dict[str, Any]], None]


def _scope_most_specific_available(
    mapped: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None]:
    scope_rank = policy.scope_rank
    unspecified_rank = len(policy.synthesis["scope_precedence"])
    selected_rank = min(
        scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank)
        for item in mapped
    )
    primary = [
        item for item in mapped
        if scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank) == selected_rank
    ]
    contextual = [
        item for item in mapped
        if scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank) > selected_rank
    ]
    return primary, contextual, selected_rank


def _scope_all_mapped_assessments(
    mapped: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None]:
    return list(mapped), [], None


def _broader_context_only(
    primary: list[dict[str, Any]],
    contextual: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return primary, contextual


def _broader_include_in_headline(
    primary: list[dict[str, Any]],
    contextual: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [*primary, *contextual], []


def _aggregate_highest_semantic_concern(
    items: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> dict[str, Any]:
    return max(items, key=lambda item: policy.rank_by_level[str(item["semantic_level"])])


def _aggregate_lowest_semantic_concern(
    items: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> dict[str, Any]:
    return min(items, key=lambda item: policy.rank_by_level[str(item["semantic_level"])])


def _aggregate_majority_semantic_level(
    items: list[dict[str, Any]],
    policy: "SynthesisPolicy",
    options: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(str(item["semantic_level"]) for item in items)
    highest_count = max(counts.values())
    tied = [level for level, count in counts.items() if count == highest_count]
    # Tie behavior is itself configurable. Conservative-high is the default.
    tie_break = str(options.get("tie_break") or "highest_semantic_concern")
    if tie_break == "lowest_semantic_concern":
        selected_level = min(tied, key=policy.rank_by_level.get)
    elif tie_break == "highest_semantic_concern":
        selected_level = max(tied, key=policy.rank_by_level.get)
    else:
        raise SynthesisPolicyError(
            "majority_semantic_level tie_break must be highest_semantic_concern or lowest_semantic_concern"
        )
    return next(item for item in items if str(item["semantic_level"]) == selected_level)


def _missing_exclude(
    mapped: list[dict[str, Any]],
    unmapped: list[dict[str, Any]],
    options: dict[str, Any],
) -> list[dict[str, Any]]:
    return mapped


def _missing_unassessed_if_any_unmapped(
    mapped: list[dict[str, Any]],
    unmapped: list[dict[str, Any]],
    options: dict[str, Any],
) -> list[dict[str, Any]]:
    return [] if unmapped else mapped


def _numeric_forbidden_across_source_scales(
    items: list[dict[str, Any]],
    options: dict[str, Any],
) -> None:
    # Deliberately no arithmetic: this operator states that semantic levels,
    # not heterogeneous source-native numeric scores, drive synthesis.
    return None


_SCOPE_SELECTION_OPERATORS: dict[str, ScopeSelector] = {
    "most_specific_available": _scope_most_specific_available,
    "all_mapped_assessments": _scope_all_mapped_assessments,
}
_BROADER_SCOPE_OPERATORS: dict[str, BroaderScopeOperator] = {
    "context_only": _broader_context_only,
    "include_in_headline": _broader_include_in_headline,
}
_AGGREGATION_OPERATORS: dict[str, Aggregator] = {
    "highest_semantic_concern": _aggregate_highest_semantic_concern,
    "lowest_semantic_concern": _aggregate_lowest_semantic_concern,
    "majority_semantic_level": _aggregate_majority_semantic_level,
}
_MISSING_OPERATORS: dict[str, MissingOperator] = {
    "exclude": _missing_exclude,
    "unassessed_if_any_unmapped": _missing_unassessed_if_any_unmapped,
}
_NUMERIC_OPERATORS: dict[str, NumericOperator] = {
    "forbidden_across_source_scales": _numeric_forbidden_across_source_scales,
}


SUPPORTED_SYNTHESIS_OPERATORS = {
    "scope_selection": tuple(sorted(_SCOPE_SELECTION_OPERATORS)),
    "same_scope_aggregation": tuple(sorted(_AGGREGATION_OPERATORS)),
    "broader_scope_policy": tuple(sorted(_BROADER_SCOPE_OPERATORS)),
    "missing_assessment_policy": tuple(sorted(_MISSING_OPERATORS)),
    "numeric_aggregation": tuple(sorted(_NUMERIC_OPERATORS)),
}


def _validate_operator(
    synthesis: dict[str, Any],
    field: str,
    registry: dict[str, Any],
) -> None:
    name = _operator_name(synthesis.get(field))
    if not name:
        raise SynthesisPolicyError(f"synthesis.{field} must name an operator")
    if name not in registry:
        raise SynthesisPolicyError(
            f"Unsupported synthesis.{field} operator '{name}'. Supported: "
            + ", ".join(sorted(registry))
        )


@dataclass(frozen=True)
class SynthesisPolicy:
    policy_id: str
    version: str
    semantic_levels: tuple[SemanticLevel, ...]
    source_rules: tuple[SourceRule, ...]
    synthesis: dict[str, Any]
    ai: dict[str, Any]
    evidence_source_roles: tuple[dict[str, Any], ...]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SynthesisPolicy":
        policy_id = str(data.get("policy_id") or "").strip()
        version = str(data.get("version") or "").strip()
        if not policy_id or not version:
            raise SynthesisPolicyError("Synthesis policy requires policy_id and version.")

        raw_levels = data.get("semantic_levels")
        if not isinstance(raw_levels, list) or not raw_levels:
            raise SynthesisPolicyError("Synthesis policy semantic_levels must be a non-empty array.")
        levels: list[SemanticLevel] = []
        seen_ids: set[str] = set()
        seen_ranks: set[int] = set()
        for item in raw_levels:
            if not isinstance(item, dict):
                raise SynthesisPolicyError("Each semantic level must be an object.")
            level_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or level_id).strip()
            rank = int(item.get("rank"))
            if not level_id or level_id in seen_ids:
                raise SynthesisPolicyError("Semantic level IDs must be unique and non-empty.")
            if rank in seen_ranks:
                raise SynthesisPolicyError("Semantic level ranks must be unique.")
            seen_ids.add(level_id)
            seen_ranks.add(rank)
            levels.append(SemanticLevel(level_id, label, rank))

        level_ids = {level.id for level in levels}
        rules: list[SourceRule] = []
        for item in data.get("source_rules") or []:
            if not isinstance(item, dict):
                raise SynthesisPolicyError("Each source rule must be an object.")
            value_map = {
                _norm(key): str(value)
                for key, value in (item.get("value_map") or {}).items()
            }
            unknown_levels = sorted(set(value_map.values()) - level_ids)
            if unknown_levels:
                raise SynthesisPolicyError(
                    "Source rule maps to unknown semantic level(s): " + ", ".join(unknown_levels)
                )
            rules.append(SourceRule(
                rule_id=str(item.get("rule_id") or "").strip(),
                source_match={str(k): str(v) for k, v in (item.get("source_match") or {}).items()},
                role=str(item.get("role") or "risk_assessment").strip(),
                value_fields=tuple(str(v) for v in (item.get("value_fields") or [])),
                value_map=value_map,
                accept_existing_semantic_level=bool(item.get("accept_existing_semantic_level", False)),
                default_scope=(str(item.get("default_scope")).strip() if item.get("default_scope") else None),
            ))

        synthesis = data.get("synthesis") or {}
        if not isinstance(synthesis, dict):
            raise SynthesisPolicyError("synthesis must be an object.")
        scope_precedence = synthesis.get("scope_precedence")
        if not isinstance(scope_precedence, list) or not scope_precedence:
            raise SynthesisPolicyError("synthesis.scope_precedence must be a non-empty array.")
        for tier in scope_precedence:
            if not isinstance(tier, list) or not tier:
                raise SynthesisPolicyError("Each scope-precedence tier must be a non-empty array.")

        headline_roles = synthesis.get("headline_roles", ["risk_assessment"])
        if not isinstance(headline_roles, list) or not [value for value in headline_roles if str(value).strip()]:
            raise SynthesisPolicyError("synthesis.headline_roles must be a non-empty array")
        synthesis = dict(synthesis)
        synthesis["headline_roles"] = [str(value).strip() for value in headline_roles if str(value).strip()]

        _validate_operator(synthesis, "missing_assessment_policy", _MISSING_OPERATORS)
        _validate_operator(synthesis, "scope_selection", _SCOPE_SELECTION_OPERATORS)
        _validate_operator(synthesis, "same_scope_aggregation", _AGGREGATION_OPERATORS)
        _validate_operator(synthesis, "broader_scope_policy", _BROADER_SCOPE_OPERATORS)
        _validate_operator(synthesis, "numeric_aggregation", _NUMERIC_OPERATORS)

        ai = data.get("ai") or {}
        if not isinstance(ai, dict):
            raise SynthesisPolicyError("ai must be an object.")

        roles = data.get("evidence_source_roles") or []
        if not isinstance(roles, list):
            raise SynthesisPolicyError("evidence_source_roles must be an array.")

        return cls(
            policy_id=policy_id,
            version=version,
            semantic_levels=tuple(sorted(levels, key=lambda level: level.rank)),
            source_rules=tuple(rules),
            synthesis=synthesis,
            ai=dict(ai),
            evidence_source_roles=tuple(dict(item) for item in roles if isinstance(item, dict)),
            raw=dict(data),
        )

    @property
    def level_by_id(self) -> dict[str, SemanticLevel]:
        return {level.id: level for level in self.semantic_levels}

    @property
    def rank_by_level(self) -> dict[str, int]:
        return {level.id: level.rank for level in self.semantic_levels}

    @property
    def scope_rank(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for rank, tier in enumerate(self.synthesis["scope_precedence"]):
            for scope in tier:
                result[str(scope)] = rank
        return result

    @property
    def headline_roles(self) -> set[str]:
        return {str(value) for value in self.synthesis.get("headline_roles") or []}

    def source_rule_for(self, assessment: dict[str, Any]) -> SourceRule | None:
        for rule in self.source_rules:
            if rule.matches(assessment):
                return rule
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "semantic_levels": [
                {"id": level.id, "label": level.label, "rank": level.rank}
                for level in self.semantic_levels
            ],
            "synthesis": dict(self.synthesis),
            "supported_operators": SUPPORTED_SYNTHESIS_OPERATORS,
            "ai": dict(self.ai),
        }


def load_synthesis_policy(path: str | Path = DEFAULT_SYNTHESIS_POLICY_PATH) -> SynthesisPolicy:
    policy_path = Path(path).expanduser()
    if not policy_path.is_file():
        raise FileNotFoundError(f"Risk synthesis policy not found: {policy_path.resolve(strict=False)}")
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SynthesisPolicyError("Risk synthesis policy must contain a JSON object.")
    return SynthesisPolicy.from_dict(data)


def _compact_assessment(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "canonical_id",
        "source_id",
        "source_type",
        "source_label",
        "source_record_id",
        "native_label",
        "native_score",
        "native_scale",
        "normalized_band",
        "normalized_score",
        "semantic_level",
        "semantic_label",
        "scope_type",
        "scope_name",
        "scope_basis",
        "mapping_rule_id",
        "mapping_version",
        "projection_version",
        "policy_rule_id",
        "policy_mapping_basis",
        "policy_role",
        "ai_evidence_ref",
        "ai_rationale",
    )
    return {key: item.get(key) for key in keys if item.get(key) is not None}


def normalize_assessment(
    assessment: dict[str, Any],
    policy: SynthesisPolicy,
) -> dict[str, Any]:
    item = dict(assessment)
    rule = policy.source_rule_for(item)
    if rule is None:
        item["policy_status"] = "unmapped_source"
        return item
    item["policy_rule_id"] = rule.rule_id
    item["policy_role"] = rule.role

    level: str | None = None
    mapping_basis: str | None = None
    for field in rule.value_fields:
        value = item.get(field)
        if value is None:
            continue
        mapped = rule.value_map.get(_norm(value))
        if mapped:
            level = mapped
            mapping_basis = f"{field}:value_map"
            break
        if (
            field == "semantic_level"
            and rule.accept_existing_semantic_level
            and str(value) in policy.level_by_id
        ):
            level = str(value)
            mapping_basis = "semantic_level:accepted_existing"
            break

    if level is None and rule.accept_existing_semantic_level:
        existing = str(item.get("semantic_level") or "").strip()
        if existing in policy.level_by_id:
            level = existing
            mapping_basis = "semantic_level:accepted_existing"

    if rule.default_scope and not item.get("scope_type"):
        item["scope_type"] = rule.default_scope
    if level is None:
        item.pop("semantic_level", None)
        item.pop("semantic_label", None)
        item["policy_status"] = "unmapped_value"
        return item

    item["semantic_level"] = level
    item["semantic_label"] = policy.level_by_id[level].label
    item["policy_mapping_basis"] = mapping_basis
    item["policy_status"] = "mapped"
    return item


def map_risk_term(
    term: Any,
    policy: SynthesisPolicy,
    *,
    source_context: dict[str, Any] | None = None,
    value_field: str = "native_label",
) -> dict[str, Any]:
    """Map one source-native risk term through the same governed source rules.

    This helper is intended for diagnostics, documentation examples and future
    integrations. It never guesses an unknown term and never changes stored
    source-native evidence.
    """
    assessment = dict(source_context or {})
    assessment[value_field] = term
    mapped = normalize_assessment(assessment, policy)
    return {
        "input_term": term,
        "normalized_term": _norm(term),
        "mapped": mapped.get("policy_status") == "mapped",
        "semantic_level": mapped.get("semantic_level"),
        "semantic_label": mapped.get("semantic_label"),
        "rule_id": mapped.get("policy_rule_id"),
        "mapping_basis": mapped.get("policy_mapping_basis"),
        "policy_status": mapped.get("policy_status"),
    }


def synthesize_assessments(
    assessments: Iterable[dict[str, Any]],
    policy: SynthesisPolicy,
    *,
    extra_normalized_assessments: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Execute the versioned, operator-driven synthesis policy."""
    normalized = [normalize_assessment(dict(item), policy) for item in assessments]
    for item in extra_normalized_assessments:
        row = dict(item)
        level = str(row.get("semantic_level") or "")
        if level not in policy.level_by_id:
            continue
        row.setdefault("semantic_label", policy.level_by_id[level].label)
        row.setdefault("policy_status", "ai_interpreted")
        row.setdefault("policy_role", next(iter(policy.headline_roles), "risk_assessment"))
        normalized.append(row)

    headline_roles = policy.headline_roles
    mapped = [
        item for item in normalized
        if item.get("policy_status") in {"mapped", "ai_interpreted"}
        and str(item.get("policy_role") or "") in headline_roles
        and str(item.get("semantic_level") or "") in policy.level_by_id
    ]
    unmapped = [
        item for item in normalized
        if str(item.get("policy_role") or "") in headline_roles
        and item.get("policy_status") not in {"mapped", "ai_interpreted"}
    ]

    missing_spec = policy.synthesis["missing_assessment_policy"]
    missing_name = _operator_name(missing_spec)
    mapped = _MISSING_OPERATORS[missing_name](mapped, unmapped, _operator_options(missing_spec))

    numeric_spec = policy.synthesis["numeric_aggregation"]
    numeric_name = _operator_name(numeric_spec)
    _NUMERIC_OPERATORS[numeric_name](mapped, _operator_options(numeric_spec))

    if not mapped:
        return {
            "assessed": False,
            "semantic_level": None,
            "semantic_label": None,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "method": "config_driven_scope_aware_synthesis",
            "basis": "no_policy_eligible_mapped_assessment",
            "contributors": [],
            "contextual_contributors": [],
            "unmapped_assessments": [_compact_assessment(item) for item in unmapped],
            "headline_roles": sorted(headline_roles),
            "missing_evidence_policy": missing_name,
            "numeric_aggregation": numeric_name,
        }

    scope_spec = policy.synthesis["scope_selection"]
    scope_name = _operator_name(scope_spec)
    primary, contextual, selected_scope_rank = _SCOPE_SELECTION_OPERATORS[scope_name](
        mapped,
        policy,
        _operator_options(scope_spec),
    )

    broader_spec = policy.synthesis["broader_scope_policy"]
    broader_name = _operator_name(broader_spec)
    primary, contextual = _BROADER_SCOPE_OPERATORS[broader_name](
        primary,
        contextual,
        policy,
        _operator_options(broader_spec),
    )
    if not primary:
        raise SynthesisPolicyError(
            f"Configured scope/broader-scope operators produced no headline candidates: {scope_name}/{broader_name}"
        )

    aggregation_spec = policy.synthesis["same_scope_aggregation"]
    aggregation_name = _operator_name(aggregation_spec)
    selected = _AGGREGATION_OPERATORS[aggregation_name](
        primary,
        policy,
        _operator_options(aggregation_spec),
    )
    selected_level = str(selected["semantic_level"])

    rank_by_level = policy.rank_by_level
    primary_levels = sorted(
        {str(item["semantic_level"]) for item in primary},
        key=rank_by_level.get,
    )
    contextual_levels = sorted(
        {str(item["semantic_level"]) for item in contextual},
        key=rank_by_level.get,
    )
    selected_scope_types = sorted({str(item.get("scope_type") or "unspecified") for item in primary})

    return {
        "assessed": True,
        "semantic_level": selected_level,
        "semantic_label": policy.level_by_id[selected_level].label,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
        "method": "config_driven_scope_aware_synthesis",
        "basis": f"scope={scope_name};broader={broader_name};aggregation={aggregation_name}",
        "selected_scope_rank": selected_scope_rank,
        "selected_scope_types": selected_scope_types,
        "contributing_levels": primary_levels,
        "contextual_levels": contextual_levels,
        "source_divergence": len(primary_levels) > 1,
        "scope_divergence": len({str(item.get("scope_type") or "") for item in mapped}) > 1,
        "cross_scope_level_divergence": bool(
            contextual_levels and any(level not in set(primary_levels) for level in contextual_levels)
        ),
        "contributors": [_compact_assessment(item) for item in primary],
        "contextual_contributors": [_compact_assessment(item) for item in contextual],
        "unmapped_assessments": [_compact_assessment(item) for item in unmapped],
        "headline_roles": sorted(headline_roles),
        "missing_evidence_policy": missing_name,
        "scope_selection": scope_name,
        "same_scope_aggregation": aggregation_name,
        "broader_scope_policy": broader_name,
        "numeric_aggregation": numeric_name,
    }
