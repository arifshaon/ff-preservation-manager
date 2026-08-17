from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    downloads: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "metadata": deepcopy(self.metadata),
            "preview": deepcopy(self.preview),
            "downloads": deepcopy(self.downloads),
        }


Runner = Callable[[str, Callable[..., None], Path], dict[str, Any] | None]


class JobManager:
    """Small in-process background job queue for the local web UI.

    Jobs execute in worker threads and write artifacts into one directory per job.
    Status is held in memory and mirrored to ``job.json`` for operational audit.
    The manager deliberately avoids a second persistence/database dependency.
    """

    def __init__(self, output_root: str | Path, *, max_workers: int = 2) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="risk-web")

    def submit(self, kind: str, runner: Runner, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = uuid4().hex
        record = JobRecord(job_id=job_id, kind=str(kind), metadata=deepcopy(metadata or {}))
        with self._lock:
            self._jobs[job_id] = record
            self._persist_locked(record)
        self._executor.submit(self._run, job_id, runner)
        return self.get(job_id)

    def _run(self, job_id: str, runner: Runner) -> None:
        job_dir = self.output_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        self.update(job_id, status="running", progress=1, message="Starting", started_at=_now())
        try:
            payload = runner(job_id, lambda **changes: self.update(job_id, **changes), job_dir) or {}
            self.update(
                job_id,
                status="completed",
                progress=100,
                message=str(payload.get("message") or "Completed"),
                preview=payload.get("preview") or {},
                downloads=payload.get("downloads") or {},
                completed_at=_now(),
            )
        except Exception as exc:
            self.update(
                job_id,
                status="failed",
                progress=100,
                message="Failed",
                error=f"{type(exc).__name__}: {exc}",
                completed_at=_now(),
            )

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            if "progress" in changes:
                try:
                    changes["progress"] = max(0, min(100, int(changes["progress"])))
                except (TypeError, ValueError):
                    changes.pop("progress")
            for key, value in changes.items():
                if hasattr(record, key):
                    setattr(record, key, deepcopy(value))
            record.updated_at = _now()
            self._persist_locked(record)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(job_id)
            return record.to_dict()

    def list(self, *, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(self._jobs.values(), key=lambda row: row.created_at, reverse=True)
            return [row.to_dict() for row in rows[: max(1, int(limit))]]

    def artifact_path(self, job_id: str, artifact: str) -> Path:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(job_id)
            filename = record.downloads.get(str(artifact))
            if not filename:
                raise KeyError(artifact)
        path = (self.output_root / job_id / filename).resolve()
        root = (self.output_root / job_id).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _persist_locked(self, record: JobRecord) -> None:
        directory = self.output_root / record.job_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(
            json.dumps(record.to_dict(), indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
