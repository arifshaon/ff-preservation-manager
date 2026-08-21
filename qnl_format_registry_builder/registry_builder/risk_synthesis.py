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

# Lower rank means more specific to the canonical format being assessed.
# exact_format and format_version are intentionally the same headline tier:
# both are specific enough to outrank family/group/context assertions.
SCOPE_SPECIFICITY_ORDER: dict[str, int] = {
    "exact_format": 0,
    "format_version": 0,
    "institutional_format": 0,
    "format_family": 1,
    "format_group": 2,
    "content_type": 3,
    "contextual": 4,
}

SCOPE_TIER_LABELS: dict[int, str] = {
    0: "exact_or_version",
    1: "format_family",
    2: "format_group",
    3: "content_type",
    4: "contextual",
    5: "unspecified",
}

SYNTHESIS_METHOD = "semantic_risk_synthesis_v2_scope_aware"


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


def _scope_rank(assessment: dict[str, Any]) -> int:
    scope = str(assessment.get("scope_type") or "").strip()
    return SCOPE_SPECIFICITY_ORDER.get(scope, 5)


def _source_text(assessment: dict[str, Any]) -> str:
    source = assessment.get("source_label") or assessment.get("source_id") or assessment.get("source_type") or "unknown source"
    native = assessment.get("native_label")
    semantic_level = normalize_semantic_level(assessment.get("semantic_level"))
    semantic = SEMANTIC_RISK_LABELS[semantic_level] if semantic_level else "Unmapped concern"
    if native and str(native).strip().lower() != semantic.lower():
        return f"{source}: {native} -> {semantic}"
    return f"{source}: {native or semantic}"


def synthesize_risk_assessments(assessments: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Create a transparent scope-aware semantic decision-support view.

    Source-native assessments are never averaged or overwritten. Only assessments
    with an explicit semantic level are considered. The headline semantic risk is
    calculated from the most specific available assessment scope. Broader family,
    group, content-type, or contextual assessments remain visible as contextual
    contributors and cannot silently override a more specific exact-format or
    format-version assessment.

    Within the selected scope tier, the highest semantic concern is retained as a
    conservative upper bound. This keeps the method auditable while preventing a
    broad risk statement such as "PDF is Vulnerable" from automatically raising a
    separately assessed exact PDF/A version from Low to Moderate.
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
            "cross_scope_level_divergence": False,
            "contributors": [],
            "contextual_contributors": [],
            "explanation": (
                "No source assessment has been mapped to the shared semantic risk scale. "
                "Source-native assessments remain available individually."
            ),
        }

    selected_scope_rank = min(_scope_rank(item) for item in scored)
    primary = [item for item in scored if _scope_rank(item) == selected_scope_rank]
    contextual = [item for item in scored if _scope_rank(item) > selected_scope_rank]

    primary_levels = [normalize_semantic_level(item.get("semantic_level")) for item in primary]
    primary_ranks = [SEMANTIC_RISK_ORDER[level] for level in primary_levels if level is not None]
    selected_rank = max(primary_ranks)
    selected_level = next(level for level, rank in SEMANTIC_RISK_ORDER.items() if rank == selected_rank)
    distinct_primary_levels = sorted(
        set(level for level in primary_levels if level is not None),
        key=SEMANTIC_RISK_ORDER.get,
    )
    primary_spread = max(primary_ranks) - min(primary_ranks)
    source_divergence = len(distinct_primary_levels) > 1

    all_scope_types = {str(item.get("scope_type")) for item in scored if item.get("scope_type")}
    scope_divergence = len(all_scope_types) > 1

    contextual_levels = sorted(
        {
            level
            for item in contextual
            if (level := normalize_semantic_level(item.get("semantic_level"))) is not None
        },
        key=SEMANTIC_RISK_ORDER.get,
    )
    cross_scope_level_divergence = bool(
        contextual_levels
        and any(level not in set(distinct_primary_levels) for level in contextual_levels)
    )

    if len(primary) == 1:
        confidence = "medium"
    elif primary_spread == 0:
        confidence = "high"
    elif primary_spread == 1:
        confidence = "medium"
    else:
        confidence = "low"

    primary_text = "; ".join(_source_text(item) for item in primary)
    selected_scope_types = sorted(
        {str(item.get("scope_type") or "unspecified") for item in primary}
    )
    selected_scope_tier = SCOPE_TIER_LABELS.get(selected_scope_rank, "unspecified")

    explanation = (
        f"{SEMANTIC_RISK_LABELS[selected_level]} selected as a conservative semantic upper bound from "
        f"the most specific available scope tier ({selected_scope_tier}) using {len(primary)} assessment(s): "
        f"{primary_text}. Native source assessments are retained separately and are not numerically averaged."
    )
    if contextual:
        contextual_text = "; ".join(_source_text(item) for item in contextual)
        explanation += (
            f" {len(contextual)} broader-scope assessment(s) are retained as context and do not override the "
            f"headline result: {contextual_text}."
        )
    if scope_divergence:
        explanation += " Contributing assessments have different declared scopes; inspect scope_type/scope_name before operational use."

    return {
        "assessed": True,
        "semantic_level": selected_level,
        "semantic_label": SEMANTIC_RISK_LABELS[selected_level],
        "method": SYNTHESIS_METHOD,
        "basis": "scope_aware_conservative_semantic_upper_bound",
        "confidence": confidence,
        "source_divergence": source_divergence,
        "semantic_spread": primary_spread,
        "contributing_levels": distinct_primary_levels,
        "scope_divergence": scope_divergence,
        "cross_scope_level_divergence": cross_scope_level_divergence,
        "selected_scope_rank": selected_scope_rank,
        "selected_scope_tier": selected_scope_tier,
        "selected_scope_types": selected_scope_types,
        "contextual_levels": contextual_levels,
        "contributors": [_contributor_summary(item) for item in primary],
        "contextual_contributors": [_contributor_summary(item) for item in contextual],
        "explanation": explanation,
    }
