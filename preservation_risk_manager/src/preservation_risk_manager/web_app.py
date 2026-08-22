from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.web_batch_service import run_batch_web_job
from preservation_risk_manager.web_human_service import run_human_web_job
from preservation_risk_manager.web_jobs import JobManager
from preservation_risk_manager.web_lookup_service import lookup_web_puids
from preservation_risk_manager.web_reports import combine_format_id_inputs
from preservation_risk_manager.web_service import WebRuntimeConfig
from preservation_risk_manager.web_ui_curator import INDEX_HTML


class HumanJobRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    ai_mode: Literal["off", "synthesize", "fill-gaps", "review-all"] = "synthesize"
    enable_ai_identification: bool = True
    scope: Literal["global", "institution"] = "global"
    institution_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)


class BatchJobRequest(BaseModel):
    ids_text: str = ""
    uploaded_text: str = ""
    uploaded_filename: str | None = None
    ai_mode: Literal["off", "synthesize", "fill-gaps"] = "off"
    scope: Literal["global", "institution"] = "global"
    institution_id: str | None = None


def _job_or_404(manager: JobManager, job_id: str) -> dict[str, Any]:
    try:
        return manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


def _human_match_limit(config: WebRuntimeConfig) -> int:
    """Return the configured human/lookup result limit.

    Human broad-format assessment already uses AIProviderConfig's
    ``human_format_assessment_limit``. Reuse that setting for the web lookup so
    "PDF" behaves consistently across the Ask and PUID Lookup workflows. When
    no AI config is present, use the web runtime's ``human_match_limit``.
    """
    if not config.ai_config:
        return max(1, int(config.human_match_limit))
    ai_cfg = base.load_ai_config(base._require_file(config.ai_config, label="AI config file"))
    return max(1, int(ai_cfg.human_format_assessment_limit))


def create_app(
    config: WebRuntimeConfig,
    *,
    manager: JobManager | None = None,
    human_runner: Callable[..., dict[str, Any]] = run_human_web_job,
    batch_runner: Callable[..., dict[str, Any]] = run_batch_web_job,
    lookup_runner: Callable[..., dict[str, Any]] = lookup_web_puids,
) -> FastAPI:
    config.validate()
    job_manager = manager or JobManager(config.jobs_dir, max_workers=config.max_workers)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            job_manager.shutdown(wait=False)

    app = FastAPI(
        title="QNL Preservation Risk Manager",
        version="0.3.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.job_manager = job_manager
    app.state.runtime_config = config

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/config")
    def safe_config() -> dict[str, Any]:
        framework = base.load_framework(base._require_file(config.framework, label="Framework file"))
        ai_configured = bool(config.ai_config)
        human_limit = _human_match_limit(config)
        policy = base.load_synthesis_policy()
        return {
            "framework": Path(config.framework).name,
            "framework_id": framework.framework_id,
            "framework_version": framework.version,
            "calibration_status": framework.calibration_status,
            "banding_enabled": framework.banding_enabled,
            "registry_backend": "mongo/storage" if config.storage_config else "registry-json",
            "ai_configured": ai_configured,
            "human_format_assessment_limit": human_limit,
            "puid_lookup_limit": human_limit,
            "batch_max_formats": int(config.batch_max_formats),
            "max_workers": int(config.max_workers),
            "synthesis_policy": policy.summary(),
        }

    @app.get("/api/formats/lookup")
    def lookup_formats(
        q: str = Query(min_length=1, max_length=500, description="Format name, PRONOM PUID, MIME type, extension, or identifier"),
    ) -> dict[str, Any]:
        try:
            return lookup_runner(config, q, limit=_human_match_limit(config))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PUID lookup failed: {exc}") from exc

    @app.get("/api/jobs")
    def list_jobs(limit: int = 25) -> list[dict[str, Any]]:
        return job_manager.list(limit=min(max(1, int(limit)), 100))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return _job_or_404(job_manager, job_id)

    @app.post("/api/jobs/human")
    def submit_human(request: HumanJobRequest) -> dict[str, Any]:
        payload = request.model_dump()
        if payload["scope"] == "institution" and not (
            str(payload.get("institution_id") or "").strip() or config.default_institution_id
        ):
            raise HTTPException(status_code=400, detail="Institution scope requires an institution ID.")
        if (payload["ai_mode"] != "off" or payload["enable_ai_identification"]) and not config.ai_config:
            raise HTTPException(status_code=400, detail="AI features are not configured for this web application.")

        def runner(job_id: str, update, job_dir: Path):
            return human_runner(config, payload, job_id, update, job_dir)

        return job_manager.submit(
            "human",
            runner,
            metadata={"question": payload["question"], "ai_mode": payload["ai_mode"], "scope": payload["scope"]},
        )

    @app.post("/api/jobs/batch")
    def submit_batch(request: BatchJobRequest) -> dict[str, Any]:
        payload = request.model_dump()
        format_ids = combine_format_id_inputs(
            entered_text=payload.get("ids_text"),
            uploaded_text=payload.get("uploaded_text"),
            uploaded_filename=payload.get("uploaded_filename"),
        )
        if not format_ids:
            raise HTTPException(status_code=400, detail="Enter format IDs or upload a TXT/CSV file containing format IDs.")
        if len(format_ids) > int(config.batch_max_formats):
            raise HTTPException(
                status_code=400,
                detail=f"The batch contains {len(format_ids)} distinct IDs; the configured maximum is {config.batch_max_formats}.",
            )
        if payload["scope"] == "institution" and not (
            str(payload.get("institution_id") or "").strip() or config.default_institution_id
        ):
            raise HTTPException(status_code=400, detail="Institution scope requires an institution ID.")
        if payload["ai_mode"] != "off" and not config.ai_config:
            raise HTTPException(status_code=400, detail="AI synthesis is not configured for this web application.")
        worker_payload = {
            "format_ids": format_ids,
            "ai_mode": payload["ai_mode"],
            "scope": payload["scope"],
            "institution_id": payload.get("institution_id"),
        }

        def runner(job_id: str, update, job_dir: Path):
            return batch_runner(config, worker_payload, job_id, update, job_dir)

        return job_manager.submit(
            "batch",
            runner,
            metadata={
                "format_count": len(format_ids),
                "uploaded_filename": payload.get("uploaded_filename"),
                "ai_mode": payload["ai_mode"],
                "scope": payload["scope"],
            },
        )

    @app.get("/api/jobs/{job_id}/download/{artifact}")
    def download(job_id: str, artifact: str):
        _job_or_404(job_manager, job_id)
        try:
            path = job_manager.artifact_path(job_id, artifact)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        media = {
            ".csv": "text/csv",
            ".json": "application/json",
            ".html": "text/html",
            ".txt": "text/plain",
            ".zip": "application/zip",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, filename=path.name, media_type=media)

    return app
