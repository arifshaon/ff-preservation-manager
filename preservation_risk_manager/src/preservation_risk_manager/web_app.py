from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.web_jobs import JobManager
from preservation_risk_manager.web_reports import combine_format_id_inputs
from preservation_risk_manager.web_service import WebRuntimeConfig, run_batch_web_job, run_human_web_job
from preservation_risk_manager.web_ui import INDEX_HTML


class HumanJobRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    ai_mode: Literal["off", "fill-gaps", "review-all"] = "fill-gaps"
    enable_ai_identification: bool = True
    scope: Literal["global", "institution"] = "global"
    institution_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)


class BatchJobRequest(BaseModel):
    ids_text: str = ""
    uploaded_text: str = ""
    uploaded_filename: str | None = None
    ai_mode: Literal["off", "fill-gaps"] = "off"
    scope: Literal["global", "institution"] = "global"
    institution_id: str | None = None


def _job_or_404(manager: JobManager, job_id: str) -> dict[str, Any]:
    try:
        return manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


def create_app(
    config: WebRuntimeConfig,
    *,
    manager: JobManager | None = None,
    human_runner: Callable[..., dict[str, Any]] = run_human_web_job,
    batch_runner: Callable[..., dict[str, Any]] = run_batch_web_job,
) -> FastAPI:
    config.validate()
    job_manager = manager or JobManager(config.jobs_dir, max_workers=config.max_workers)
    app = FastAPI(
        title="QNL Preservation Risk Manager",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
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
        human_limit = 10
        ai_configured = bool(config.ai_config)
        if config.ai_config:
            ai_cfg = base.load_ai_config(base._require_file(config.ai_config, label="AI config file"))
            human_limit = int(ai_cfg.human_format_assessment_limit)
        return {
            "framework": Path(config.framework).name,
            "framework_id": framework.framework_id,
            "framework_version": framework.version,
            "calibration_status": framework.calibration_status,
            "banding_enabled": framework.banding_enabled,
            "registry_backend": "mongo/storage" if config.storage_config else "registry-json",
            "ai_configured": ai_configured,
            "human_format_assessment_limit": human_limit,
            "batch_max_formats": int(config.batch_max_formats),
            "max_workers": int(config.max_workers),
        }

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
            raise HTTPException(status_code=400, detail="AI fill-gaps is not configured for this web application.")
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
            ".txt": "text/plain",
            ".zip": "application/zip",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, filename=path.name, media_type=media)

    @app.on_event("shutdown")
    def shutdown_jobs() -> None:
        job_manager.shutdown(wait=False)

    return app
