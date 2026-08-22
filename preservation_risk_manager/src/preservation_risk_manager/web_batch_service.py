from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from preservation_risk_manager.batch_monitoring import run_batch_assessment
from preservation_risk_manager.web_reports import summary_row, write_report_artifacts
from preservation_risk_manager.web_service import WebRuntimeConfig, _framework, _provider, _reader


Progress = Callable[..., None]


def run_batch_web_job(
    config: WebRuntimeConfig,
    payload: dict[str, Any],
    job_id: str,
    update: Progress,
    job_dir: Path,
) -> dict[str, Any]:
    format_ids = [str(value).strip() for value in payload.get("format_ids") or [] if str(value).strip()]
    if not format_ids:
        raise ValueError("At least one format ID is required.")
    if len(format_ids) > int(config.batch_max_formats):
        raise ValueError(
            f"The batch contains {len(format_ids)} IDs; the configured maximum is {config.batch_max_formats}."
        )

    ai_mode = str(payload.get("ai_mode") or "off").strip().lower()
    if ai_mode not in {"off", "synthesize", "fill-gaps"}:
        raise ValueError("Batch web reports support ai_mode off, synthesize, or fill-gaps.")
    if ai_mode != "off" and not config.ai_config:
        raise ValueError("AI batch mode requires ai_config in the web application configuration.")

    scope = str(payload.get("scope") or "global").strip().lower()
    institution_id = str(payload.get("institution_id") or config.default_institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    update(progress=5, message=f"Loading registry for {len(format_ids)} format IDs")
    reader = _reader(config)
    framework = _framework(config)
    provider = _provider(config) if ai_mode != "off" else None

    def progress(value: int, message: str) -> None:
        update(progress=min(94, max(5, int(value))), message=message)

    report = run_batch_assessment(
        reader=reader,
        framework=framework,
        format_ids=format_ids,
        scope=scope,
        institution_id=institution_id,
        ai_mode=ai_mode,
        provider=provider,
        max_ai_evidence_items=int(config.max_ai_evidence_items),
        progress=progress,
    )

    if provider is not None and getattr(provider, "rate_limited", False):
        update(
            progress=94,
            message="AI provider rate-limited; governed results were retained for affected formats",
        )

    update(progress=96, message="Writing HTML, CSV, JSON, and ZIP reports")
    downloads = write_report_artifacts(report, job_dir)
    rows = report.get("summary") or []
    return {
        "message": f"Risk report completed for {len(rows)} format IDs",
        "downloads": downloads,
        "preview": {
            "kind": "batch",
            "input_count": len(rows),
            "successful_assessments": report["successful_assessments"],
            "failed_or_unresolved": report["failed_or_unresolved"],
            "governed_risk_counts": report.get("governed_risk_counts"),
            "ai_successful_syntheses": report.get("ai_successful_syntheses"),
            "rows": rows[:50],
            "preview_truncated": len(rows) > 50,
        },
    }
