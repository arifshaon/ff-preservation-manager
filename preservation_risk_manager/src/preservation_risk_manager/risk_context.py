from __future__ import annotations

from copy import deepcopy
from typing import Any

from preservation_risk_manager.data_access import RegistryReader


_SCOPE_SPECIFICITY = {
    "exact_format": 5,
    "format_family": 4,
    "family": 4,
    "format_group": 3,
    "group": 3,
    "content_type": 2,
    "contextual": 1,
}


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


def _scope_rank(row: dict[str, Any]) -> int:
    return _SCOPE_SPECIFICITY.get(str(row.get("scope_type") or "").lower(), 0)


def build_external_risk_context(
    reader: RegistryReader,
    format_doc: dict[str, Any],
) -> dict[str, Any]:
    """Return governed external risk assessments without changing framework scoring.

    ``risk_assessment_claims`` are source-native assessments such as NARA and DPC.
    They are intentionally exposed alongside the QNL framework result rather than
    converted into framework question answers or averaged into the framework score.
    Scope is preserved so an exact-format assessment can coexist with broader
    family/group context without either silently overriding the other.
    """

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
    assessments.sort(
        key=lambda row: (
            -_scope_rank(row),
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

    synthesized = format_doc.get("synthesized_risk")
    if not isinstance(synthesized, dict):
        synthesized = {}

    return {
        "assessment_count": len(assessments),
        "canonical_ids_checked": canonical_ids,
        "assessments": assessments,
        "semantic_levels": semantic_levels,
        "scope_types": scope_types,
        "scoped_divergence": len(semantic_levels) > 1,
        "registry_synthesized_risk": deepcopy(synthesized),
        "scoring_effect": "context_only",
        "aggregation_policy": "do_not_average_external_assessments",
    }
