from __future__ import annotations

from typing import Any, Iterable

SEMANTIC_RISK_ORDER: dict[str, int] = {
    "minimal": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}

SEMANTIC_RISK_LABELS: dict[str, str] = {
    "minimal": "Minimal concern",
    "low": "Low concern",
    "moderate": "Moderate concern",
    "high": "High concern",
    "critical": "Critical concern",
}

SYNTHESIS_METHOD = "semantic_risk_synthesis_v1"


def normalize_semantic_level(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("_", " ")
    aliases = {
        "minimal": "minimal",
        "minimal concern": "minimal",
        "lower risk": "minimal",
        "low": "low",
        "low concern": "low",
        "moderate": "moderate",
        "medium": "moderate",
        "moderate concern": "moderate",
        "high": "high",
        "high concern": "high",
        "critical": "critical",
        "critical concern": "critical",
    }
    return aliases.get(text)


def semantic_level_from_three_band(value: Any) -> str | None:
    """Map an already-normalized Low/Moderate/High label to semantic concern.

    This helper is intentionally limited to the shared three-band vocabulary
    already used by NARA/QNL in the current pipeline. Source-specific vocabularies
    such as DPC's Vulnerable/Endangered scale must be mapped explicitly by their
    own adapter/config before synthesis.
    """

    text = str(value or "").strip().lower()
    if not text:
        return None
    if "high" in text:
        return "high"
    if "moderate" in text or "medium" in text:
        return "moderate"
    if "low" in text:
        return "low"
    return None


def _first_value(data: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _source_record_id_for(source_id: Any, source_records: Iterable[dict[str, Any]]) -> str | None:
    matches = [
        item.get("source_record_id")
        for item in source_records
        if str(item.get("source_id") or "") == str(source_id or "") and item.get("source_record_id")
    ]
    unique = list(dict.fromkeys(str(value) for value in matches))
    return unique[0] if len(unique) == 1 else None


def _assessment_from_external_hazard(
    hazard: dict[str, Any],
    *,
    source_records: Iterable[dict[str, Any]],
    canonical_name: str | None,
) -> dict[str, Any]:
    source_id = hazard.get("source_id")
    source_type = hazard.get("source_type")
    source_record_id = hazard.get("source_record_id") or _source_record_id_for(source_id, source_records)
    native_label = _first_value(
        hazard,
        (
            "native_label",
            "external_native_band",
            "native_band",
            "risk_level",
            "external_risk_level",
            "external_band",
            "band",
        ),
    )
    native_score = _first_value(
        hazard,
        (
            "native_score",
            "external_rating_native",
            "external_native_rating",
            "native_rating",
            "rating",
            "normalized_rating",
            "score",
        ),
    )
    native_scale = _first_value(
        hazard,
        (
            "native_scale",
            "external_rating_native_scale",
        ),
    )
    normalized_band = _first_value(
        hazard,
        ("normalized_band", "external_band", "band", "hazard_band"),
    )
    normalized_score = _first_value(
        hazard,
        ("normalized_score", "normalized_rating", "rating", "hazard_rating", "risk_score"),
    )
    semantic_level = normalize_semantic_level(hazard.get("semantic_level"))
    if semantic_level is None:
        semantic_level = semantic_level_from_three_band(normalized_band)

    assessment: dict[str, Any] = {
        "assessment_role": hazard.get("assessment_role") or "external",
        "source_id": source_id,
        "source_type": source_type,
        "source_record_id": source_record_id,
        "source_label": hazard.get("source_label") or hazard.get("source") or source_id or source_type,
        "native_label": native_label,
        "native_score": _float_value(native_score) if native_score is not None else None,
        "native_scale": native_scale,
        "normalized_band": normalized_band,
        "normalized_score": _float_value(normalized_score) if normalized_score is not None else None,
        "semantic_level": semantic_level,
        "scope_type": hazard.get("scope_type") or "exact_format",
        "scope_name": hazard.get("scope_name") or canonical_name,
        "scope_basis": hazard.get("scope_basis") or "reconciled_source_record",
        "native_assessment": dict(hazard),
    }
    if semantic_level:
        assessment["semantic_label"] = SEMANTIC_RISK_LABELS[semantic_level]
    return {key: value for key, value in assessment.items() if value is not None}


def _assessment_from_institution_policy(
    policy: dict[str, Any],
    *,
    canonical_name: str | None,
) -> dict[str, Any] | None:
    native_label = _first_value(policy, ("local_risk_level", "risk_level", "spreadsheet_risk_level"))
    semantic_level = semantic_level_from_three_band(native_label)
    if native_label is None and semantic_level is None:
        return None

    normalized_band = None
    normalized_score = None
    if semantic_level == "low":
        normalized_band, normalized_score = "Low", 1.0
    elif semantic_level == "moderate":
        normalized_band, normalized_score = "Moderate", 2.0
    elif semantic_level == "high":
        normalized_band, normalized_score = "High", 3.0

    source_record_id = policy.get("institution_format_id")
    if not source_record_id and policy.get("source_file"):
        source_record_id = str(policy.get("source_file"))
        if policy.get("source_row") is not None:
            source_record_id += f"#{policy.get('source_row')}"

    assessment: dict[str, Any] = {
        "assessment_role": "institutional",
        "source_id": policy.get("institution_id") or "institution_policy",
        "source_type": "institution_policy",
        "source_record_id": source_record_id,
        "source_label": policy.get("institution_name") or policy.get("institution_id") or "Institutional assessment",
        "native_label": native_label,
        "normalized_band": normalized_band,
        "normalized_score": normalized_score,
        "semantic_level": semantic_level,
        "scope_type": "institutional_format",
        "scope_name": canonical_name,
        "scope_basis": "institution_policy_overlay",
        "native_assessment": dict(policy),
    }
    if semantic_level:
        assessment["semantic_label"] = SEMANTIC_RISK_LABELS[semantic_level]
    return {key: value for key, value in assessment.items() if value is not None}


def risk_assessments_from_canonical_fields(
    *,
    explicit_assessments: Iterable[dict[str, Any]] = (),
    external_hazard: Iterable[dict[str, Any]] = (),
    institution_policy_overlays: Iterable[dict[str, Any]] = (),
    source_records: Iterable[dict[str, Any]] = (),
    canonical_name: str | None = None,
) -> list[dict[str, Any]]:
    """Build the preferred source-native risk-assessment view.

    Explicit risk_assessments take precedence for future adapters. Legacy hazard
    and institution-policy structures are projected into the same view so the
    migration is backwards compatible and existing source data is not rewritten.
    """

    assessments: list[dict[str, Any]] = [dict(item) for item in explicit_assessments]
    assessments.extend(
        _assessment_from_external_hazard(
            dict(hazard),
            source_records=source_records,
            canonical_name=canonical_name,
        )
        for hazard in external_hazard
        if hazard
    )
    for policy in institution_policy_overlays:
        assessment = _assessment_from_institution_policy(dict(policy), canonical_name=canonical_name)
        if assessment:
            assessments.append(assessment)
    return dedupe_risk_assessments(assessments)


def _assessment_key(assessment: dict[str, Any]) -> tuple[Any, ...]:
    return (
        assessment.get("assessment_role"),
        assessment.get("source_type"),
        assessment.get("source_id"),
        assessment.get("source_record_id"),
        assessment.get("native_label"),
        assessment.get("native_score"),
        assessment.get("native_scale"),
        assessment.get("scope_type"),
        assessment.get("scope_name"),
    )


def dedupe_risk_assessments(assessments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for assessment in assessments:
        item = dict(assessment)
        semantic = normalize_semantic_level(item.get("semantic_level"))
        if semantic:
            item["semantic_level"] = semantic
            item.setdefault("semantic_label", SEMANTIC_RISK_LABELS[semantic])
        key = _assessment_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _contributor_summary(assessment: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "assessment_role",
        "source_id",
        "source_type",
        "source_record_id",
        "source_label",
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
    )
    return {key: assessment.get(key) for key in keys if assessment.get(key) is not None}


def synthesize_risk_assessments(assessments: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Create a transparent semantic decision-support view.

    Source-native assessments are never averaged or overwritten. The synthesis
    uses only assessments that already carry an explicit semantic level and
    selects the highest semantic concern as a conservative upper bound. This is
    intentionally simple and auditable; source-specific vocabulary mapping must
    happen before this function is called.
    """

    retained = dedupe_risk_assessments(assessments)
    scored = [
        assessment
        for assessment in retained
        if normalize_semantic_level(assessment.get("semantic_level")) in SEMANTIC_RISK_ORDER
    ]
    if not scored:
        return {
            "assessed": False,
            "semantic_level": None,
            "semantic_label": None,
            "method": SYNTHESIS_METHOD,
            "basis": "no_semantically_mapped_assessment",
            "confidence": "low",
            "source_divergence": False,
            "scope_divergence": False,
            "contributors": [],
            "explanation": (
                "No source assessment has been mapped to the shared semantic risk scale. "
                "Source-native assessments remain available individually."
            ),
        }

    levels = [normalize_semantic_level(item.get("semantic_level")) for item in scored]
    ranks = [SEMANTIC_RISK_ORDER[level] for level in levels if level is not None]
    selected_rank = max(ranks)
    selected_level = next(level for level, rank in SEMANTIC_RISK_ORDER.items() if rank == selected_rank)
    distinct_levels = sorted(set(level for level in levels if level is not None), key=SEMANTIC_RISK_ORDER.get)
    spread = max(ranks) - min(ranks)
    source_divergence = len(distinct_levels) > 1

    scope_types = {str(item.get("scope_type")) for item in scored if item.get("scope_type")}
    scope_divergence = len(scope_types) > 1

    if len(scored) == 1:
        confidence = "medium"
    elif spread == 0:
        confidence = "high"
    elif spread == 1:
        confidence = "medium"
    else:
        confidence = "low"

    contributor_text: list[str] = []
    for item in scored:
        source = item.get("source_label") or item.get("source_id") or item.get("source_type") or "unknown source"
        native = item.get("native_label")
        semantic = SEMANTIC_RISK_LABELS[normalize_semantic_level(item.get("semantic_level"))]
        if native and str(native).strip().lower() != semantic.lower():
            contributor_text.append(f"{source}: {native} -> {semantic}")
        else:
            contributor_text.append(f"{source}: {native or semantic}")

    explanation = (
        f"{SEMANTIC_RISK_LABELS[selected_level]} selected as a conservative semantic upper bound from "
        f"{len(scored)} retained assessment(s): " + "; ".join(contributor_text) + ". "
        "Native source assessments are retained separately and are not numerically averaged."
    )
    if scope_divergence:
        explanation += " Contributing assessments have different declared scopes; inspect scope_type/scope_name before operational use."

    return {
        "assessed": True,
        "semantic_level": selected_level,
        "semantic_label": SEMANTIC_RISK_LABELS[selected_level],
        "method": SYNTHESIS_METHOD,
        "basis": "conservative_semantic_upper_bound",
        "confidence": confidence,
        "source_divergence": source_divergence,
        "semantic_spread": spread,
        "contributing_levels": distinct_levels,
        "scope_divergence": scope_divergence,
        "contributors": [_contributor_summary(item) for item in scored],
        "explanation": explanation,
    }
