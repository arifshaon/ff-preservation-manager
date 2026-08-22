from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any, Callable

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.integration_cli_human import (
    _assess_human_puid_matches,
    _ask as run_human_query,
    _programmatic_simple_risk_route,
    _resolve_human_request_format,
)
from preservation_risk_manager.web_service import WebRuntimeConfig, _framework, _reader, _write_human_artifacts


Progress = Callable[..., None]


def _run_without_ai(
    config: WebRuntimeConfig,
    *,
    question: str,
    scope: str,
    institution_id: str | None,
    match_limit: int,
    max_ai_evidence_items: int,
) -> dict[str, Any]:
    """Run the simple human risk-question pattern without an AI provider.

    This intentionally supports only the programmatically recognized
    ``risk of <format>`` shape. More general natural-language routing still
    requires a configured AI provider.
    """
    reader = _reader(config)
    framework = _framework(config)
    routed = _programmatic_simple_risk_route(
        question,
        default_scope=scope,
        default_institution_id=institution_id if scope == "institution" else None,
        default_limit=match_limit,
    )
    if routed is None:
        raise ValueError(
            "AI is not configured. Use a direct question such as "
            "'What is the preservation risk of fmt/276?' or configure an AI provider for general natural-language routing."
        )

    routed_request = base.normalize_request(routed["request"])
    prepared_request, identification = _resolve_human_request_format(reader, routed_request, plugin=None)
    response = _assess_human_puid_matches(
        reader,
        framework,
        routed_request,
        identification,
        provider=None,
        ai_mode="off",
        max_evidence_items=max_ai_evidence_items,
        user_question=question,
        human_format_assessment_limit=match_limit,
    )
    if response is None:
        response = base._identification_ambiguity_response(framework, routed_request, identification)
    if response is None:
        response = base.execute_request(reader, framework, prepared_request)

    response["input"] = {"mode": "human_prompt", "prompt": question}
    response["router"] = routed["router"]
    if identification is not None:
        response["identification"] = identification
    return response


def run_human_web_job(
    config: WebRuntimeConfig,
    payload: dict[str, Any],
    job_id: str,
    update: Progress,
    job_dir: Path,
) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("A human risk question is required.")
    ai_mode = str(payload.get("ai_mode") or "synthesize").strip().lower()
    if ai_mode not in {"off", "synthesize", "fill-gaps", "review-all"}:
        raise ValueError("ai_mode must be off, synthesize, fill-gaps, or review-all.")

    enable_ai_identification = bool(payload.get("enable_ai_identification", True))
    if (ai_mode != "off" or enable_ai_identification) and not config.ai_config:
        raise ValueError("AI features are not configured for this web application.")

    scope = str(payload.get("scope") or "global").strip().lower()
    institution_id = str(payload.get("institution_id") or config.default_institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    match_limit = int(payload.get("limit") or config.human_match_limit)
    max_ai_evidence_items = int(payload.get("max_ai_evidence_items") or config.max_ai_evidence_items)

    update(progress=8, message="Loading registry and framework")
    if not config.ai_config:
        update(progress=20, message="Resolving the direct human risk question without AI")
        result = _run_without_ai(
            config,
            question=question,
            scope=scope,
            institution_id=institution_id,
            match_limit=match_limit,
            max_ai_evidence_items=max_ai_evidence_items,
        )
    else:
        args = Namespace(
            question=question,
            framework=config.framework,
            registry_json=config.registry_json,
            storage_config=config.storage_config,
            ai_config=config.ai_config,
            institution=institution_id if scope == "institution" else None,
            limit=match_limit,
            json=True,
            enable_ai_identification=enable_ai_identification,
            identification_ai_min_confidence=float(
                payload.get("identification_ai_min_confidence") or config.identification_ai_min_confidence
            ),
            ai_mode=ai_mode,
            max_ai_evidence_items=max_ai_evidence_items,
        )
        update(progress=20, message="Resolving the human question and matching format IDs")
        result = run_human_query(args)

    update(progress=88, message="Rendering assessment")
    rendered = render_human_response(result)
    downloads = _write_human_artifacts(result, rendered, job_dir)
    return {
        "message": "Human risk assessment completed",
        "downloads": downloads,
        "preview": {
            "kind": "human",
            "text": rendered,
            "status": result.get("status"),
        },
    }
