from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable


DEFAULT_SYNTHESIS_POLICY_PATH = (
    Path(__file__).resolve().parent
    / "config"
    / "qnl_preservation_risk_synthesis.v1.json"
)


class SynthesisPolicyError(ValueError):
    """Raised when a preservation-risk synthesis policy is invalid."""


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


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

        if synthesis.get("missing_assessment_policy") != "exclude":
            raise SynthesisPolicyError("Only missing_assessment_policy='exclude' is supported.")
        if synthesis.get("scope_selection") != "most_specific_available":
            raise SynthesisPolicyError("Only scope_selection='most_specific_available' is supported.")
        if synthesis.get("same_scope_aggregation") != "highest_semantic_concern":
            raise SynthesisPolicyError("Only same_scope_aggregation='highest_semantic_concern' is supported.")
        if synthesis.get("broader_scope_policy") != "context_only":
            raise SynthesisPolicyError("Only broader_scope_policy='context_only' is supported.")
        if synthesis.get("numeric_aggregation") != "forbidden_across_source_scales":
            raise SynthesisPolicyError(
                "numeric_aggregation must be 'forbidden_across_source_scales'."
            )

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
            synthesis=dict(synthesis),
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
    if rule.role != "risk_assessment":
        item["policy_status"] = "non_risk_source_role"
        return item

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


def synthesize_assessments(
    assessments: Iterable[dict[str, Any]],
    policy: SynthesisPolicy,
    *,
    extra_normalized_assessments: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Apply the versioned config policy to source assessments.

    Missing sources are absent from ``assessments`` and therefore contribute
    nothing. Native source values are retained; only semantic normalization and
    the policy-declared scope/aggregation rules determine the headline result.
    """
    normalized = [normalize_assessment(dict(item), policy) for item in assessments]
    for item in extra_normalized_assessments:
        row = dict(item)
        level = str(row.get("semantic_level") or "")
        if level not in policy.level_by_id:
            continue
        row.setdefault("semantic_label", policy.level_by_id[level].label)
        row.setdefault("policy_status", "ai_interpreted")
        normalized.append(row)

    mapped = [
        item for item in normalized
        if item.get("policy_status") in {"mapped", "ai_interpreted"}
        and str(item.get("semantic_level") or "") in policy.level_by_id
    ]
    unmapped = [
        item for item in normalized
        if item.get("policy_role", "risk_assessment") == "risk_assessment"
        and item.get("policy_status") not in {"mapped", "ai_interpreted"}
    ]

    if not mapped:
        return {
            "assessed": False,
            "semantic_level": None,
            "semantic_label": None,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "method": "config_driven_scope_aware_synthesis",
            "basis": "no_semantically_mapped_assessment",
            "contributors": [],
            "contextual_contributors": [],
            "unmapped_assessments": [_compact_assessment(item) for item in unmapped],
            "missing_evidence_policy": policy.synthesis["missing_assessment_policy"],
            "numeric_aggregation": policy.synthesis["numeric_aggregation"],
        }

    scope_rank = policy.scope_rank
    unspecified_rank = len(policy.synthesis["scope_precedence"])
    selected_scope_rank = min(
        scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank)
        for item in mapped
    )
    primary = [
        item for item in mapped
        if scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank) == selected_scope_rank
    ]
    contextual = [
        item for item in mapped
        if scope_rank.get(str(item.get("scope_type") or ""), unspecified_rank) > selected_scope_rank
    ]

    rank_by_level = policy.rank_by_level
    selected = max(primary, key=lambda item: rank_by_level[str(item["semantic_level"])])
    selected_level = str(selected["semantic_level"])
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
        "basis": "most_specific_scope_then_highest_semantic_concern",
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
        "missing_evidence_policy": policy.synthesis["missing_assessment_policy"],
        "same_scope_aggregation": policy.synthesis["same_scope_aggregation"],
        "broader_scope_policy": policy.synthesis["broader_scope_policy"],
        "numeric_aggregation": policy.synthesis["numeric_aggregation"],
    }
