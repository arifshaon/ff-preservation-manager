from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.synthesis_policy import SynthesisPolicy, load_synthesis_policy, synthesize_assessments


def _is_current(row: dict[str, Any]) -> bool:
    return row.get("current") is not False


def _claim_key(row: dict[str, Any]) -> str:
    if row.get("_storage_key"):
        return str(row["_storage_key"])
    return "|".join(
        str(row.get(key) or "")
        for key in (
            "canonical_id",
            "source_id",
            "source_record_id",
            "mapping_rule_id",
            "projection_version",
        )
    )


def _first(row: dict[str, Any], assessment: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    return value if value is not None else assessment.get(key)


def _compact_assessment(row: dict[str, Any]) -> dict[str, Any]:
    assessment = row.get("assessment") if isinstance(row.get("assessment"), dict) else {}
    native = assessment.get("native_assessment") if isinstance(assessment.get("native_assessment"), dict) else {}

    result = {
        "canonical_id": row.get("canonical_id"),
        "source_id": _first(row, assessment, "source_id"),
        "source_type": _first(row, assessment, "source_type"),
        "source_label": assessment.get("source_label"),
        "source_record_id": _first(row, assessment, "source_record_id"),
        "scope_type": _first(row, assessment, "scope_type"),
        "scope_name": _first(row, assessment, "scope_name"),
        "scope_basis": assessment.get("scope_basis"),
        "native_label": _first(row, assessment, "native_label"),
        "native_score": _first(row, assessment, "native_score"),
        "native_scale": _first(row, assessment, "native_scale"),
        "native_direction": native.get("native_direction") or native.get("external_rating_native_direction"),
        "normalized_band": _first(row, assessment, "normalized_band"),
        "normalized_score": _first(row, assessment, "normalized_score"),
        "semantic_level": _first(row, assessment, "semantic_level"),
        "semantic_label": assessment.get("semantic_label"),
        "mapping_rule_id": _first(row, assessment, "mapping_rule_id"),
        "mapping_version": _first(row, assessment, "mapping_version"),
        "projection_version": _first(row, assessment, "projection_version"),
    }
    return {key: value for key, value in result.items() if value is not None}


def build_external_risk_context(
    reader: RegistryReader,
    format_doc: dict[str, Any],
    *,
    synthesis_policy: SynthesisPolicy | None = None,
) -> dict[str, Any]:
    """Return source-native risk assessments plus config-driven synthesis.

    ``risk_assessment_claims`` remain source-native governed evidence. They are
    never converted into framework-question answers or numerically averaged. The
    versioned synthesis policy controls normalization, scope precedence, missing
    evidence handling, same-scope aggregation and broader-scope context behavior.

    ``scoring_effect`` and ``aggregation_policy`` retain their original values for
    API compatibility: these assessments remain context-only relative to the
    separate 22-question framework score. ``policy_synthesized_risk`` is the
    independent overall source-risk synthesis.
    """

    policy = synthesis_policy or load_synthesis_policy()
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()
    canonical_ids = reader.criterion_claim_canonical_ids(format_doc)
    for canonical_id in canonical_ids:
        for row in reader.query("risk_assessment_claims", {"canonical_id": canonical_id}):
            if not _is_current(row):
                continue
            key = _claim_key(row)
            if key in seen:
                continue
            seen.add(key)
            claims.append(row)

    assessments = [_compact_assessment(row) for row in claims]
    unspecified_rank = len(policy.synthesis["scope_precedence"])
    assessments.sort(
        key=lambda row: (
            policy.scope_rank.get(str(row.get("scope_type") or ""), unspecified_rank),
            str(row.get("source_label") or row.get("source_id") or ""),
            str(row.get("source_record_id") or ""),
        )
    )

    semantic_levels = sorted({
        str(row.get("semantic_level"))
        for row in assessments
        if row.get("semantic_level")
    })
    scope_types = sorted({
        str(row.get("scope_type"))
        for row in assessments
        if row.get("scope_type")
    })

    registry_synthesized = format_doc.get("synthesized_risk")
    if not isinstance(registry_synthesized, dict):
        registry_synthesized = {}
    policy_synthesized = synthesize_assessments(assessments, policy)
    registry_level = registry_synthesized.get("semantic_level")
    policy_level = policy_synthesized.get("semantic_level")

    return {
        "assessment_count": len(assessments),
        "canonical_ids_checked": canonical_ids,
        "assessments": assessments,
        "semantic_levels": semantic_levels,
        "scope_types": scope_types,
        "scoped_divergence": len(semantic_levels) > 1,
        "synthesis_policy": policy.summary(),
        "policy_synthesized_risk": policy_synthesized,
        "registry_synthesized_risk": deepcopy(registry_synthesized),
        "registry_synthesis_parity": {
            "registry_level": registry_level,
            "policy_level": policy_level,
            "semantic_level_match": registry_level == policy_level,
        },
        "scoring_effect": "context_only",
        "aggregation_policy": "do_not_average_external_assessments",
        "synthesis_rules": {
            "missing_assessment_policy": policy.synthesis["missing_assessment_policy"],
            "scope_selection": policy.synthesis["scope_selection"],
            "same_scope_aggregation": policy.synthesis["same_scope_aggregation"],
            "broader_scope_policy": policy.synthesis["broader_scope_policy"],
            "numeric_aggregation": policy.synthesis["numeric_aggregation"],
        },
    }
