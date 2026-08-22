from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any, Callable

from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.integration_cli_human import _ask as run_human_query
from preservation_risk_manager.web_service import WebRuntimeConfig, _write_human_artifacts


Progress = Callable[..., None]


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
    if (ai_mode != "off" or bool(payload.get("enable_ai_identification", True))) and not config.ai_config:
        raise ValueError("Human AI features require ai_config in the web application configuration.")

    scope = str(payload.get("scope") or "global").strip().lower()
    institution_id = str(payload.get("institution_id") or config.default_institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    update(progress=8, message="Loading registry and framework")
    args = Namespace(
        question=question,
        framework=config.framework,
        registry_json=config.registry_json,
        storage_config=config.storage_config,
        ai_config=config.ai_config,
        institution=institution_id if scope == "institution" else None,
        limit=int(payload.get("limit") or config.human_match_limit),
        json=True,
        enable_ai_identification=bool(payload.get("enable_ai_identification", True)),
        identification_ai_min_confidence=float(
            payload.get("identification_ai_min_confidence") or config.identification_ai_min_confidence
        ),
        ai_mode=ai_mode,
        max_ai_evidence_items=int(payload.get("max_ai_evidence_items") or config.max_ai_evidence_items),
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
