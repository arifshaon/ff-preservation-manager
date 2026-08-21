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
