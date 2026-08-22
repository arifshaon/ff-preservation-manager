from __future__ import annotations

from typing import Any

from preservation_risk_manager.ai.capability_synthesis import synthesize_with_capabilities as _synthesize_raw
from preservation_risk_manager.synthesis_policy import SynthesisPolicy


def _derived_baseline_relation(
    *,
    ai_level: str | None,
    baseline_level: str | None,
    policy: SynthesisPolicy,
) -> str:
    if not ai_level or not baseline_level:
        return "not_comparable"
    if ai_level == baseline_level:
        return "same"
    ranks = policy.rank_by_level
    if ai_level not in ranks or baseline_level not in ranks:
        return "not_comparable"
    return "higher_concern" if ranks[ai_level] > ranks[baseline_level] else "lower_concern"


def _normalize_relation(result: dict[str, Any], policy: SynthesisPolicy) -> None:
    overall = result.get("overall_synthesized_risk")
    if not isinstance(overall, dict):
        return
    governed = result.get("governed_synthesis")
    if not isinstance(governed, dict):
        governed = overall.get("governed_baseline") if isinstance(overall.get("governed_baseline"), dict) else {}

    ai_level = str(overall.get("semantic_level") or "").strip() or None
    baseline_level = str(governed.get("semantic_level") or "").strip() or None
    derived = _derived_baseline_relation(
        ai_level=ai_level,
        baseline_level=baseline_level,
        policy=policy,
    )
    reported = str(overall.get("governed_baseline_relation") or "").strip() or None
    if reported and reported != derived:
        warnings = [str(item) for item in overall.get("quality_warnings") or []]
        warnings.append(
            "AI self-reported governed-baseline relation "
            f"'{reported}' was inconsistent with the returned semantic levels "
            f"(AI={ai_level or 'unassessed'}, governed={baseline_level or 'unassessed'}); "
            f"the application normalized the relation to '{derived}'."
        )
        overall["quality_warnings"] = warnings
        overall["ai_reported_governed_baseline_relation"] = reported
    overall["governed_baseline_relation"] = derived


def _surface_consulted_urls(result: dict[str, Any]) -> None:
    external = result.get("external_capability")
    if not isinstance(external, dict):
        return

    sources = [dict(item) for item in external.get("sources") or [] if isinstance(item, dict)]
    known_urls = {str(item.get("url") or "").strip() for item in sources if str(item.get("url") or "").strip()}
    for url in external.get("consulted_urls") or []:
        text = str(url or "").strip()
        if not text or text in known_urls:
            continue
        sources.append({
            "ref": f"W{len(sources) + 1:03d}",
            "url": text,
            "title": "Consulted web source",
            "source_kind": "consulted_url",
        })
        known_urls.add(text)

    if sources:
        external["sources"] = sources
        overall = result.get("overall_synthesized_risk")
        if isinstance(overall, dict):
            overall["external_sources"] = [dict(item) for item in sources]


def synthesize_with_capabilities(*args, **kwargs) -> dict[str, Any]:
    """Public capability-driven synthesis with deterministic result consistency checks."""
    policy = kwargs.get("policy")
    if not isinstance(policy, SynthesisPolicy):
        raise TypeError("synthesize_with_capabilities requires a SynthesisPolicy via keyword argument 'policy'.")
    result = _synthesize_raw(*args, **kwargs)
    _normalize_relation(result, policy)
    _surface_consulted_urls(result)
    return result


def synthesize_with_web_research(*args, **kwargs) -> dict[str, Any]:
    """Backward-compatible public alias for capability-driven synthesis."""
    return synthesize_with_capabilities(*args, **kwargs)
