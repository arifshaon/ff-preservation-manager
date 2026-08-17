import time

from fastapi.testclient import TestClient

from preservation_risk_manager.web_app import create_app
from preservation_risk_manager.web_jobs import JobManager
from preservation_risk_manager.web_service import WebRuntimeConfig


def _config(tmp_path):
    framework = tmp_path / "framework.json"
    storage = tmp_path / "storage.json"
    ai = tmp_path / "ai.json"
    framework.write_text("{}", encoding="utf-8")
    storage.write_text("{}", encoding="utf-8")
    ai.write_text('{"provider":"mock"}', encoding="utf-8")
    return WebRuntimeConfig(
        framework=str(framework),
        storage_config=str(storage),
        ai_config=str(ai),
        jobs_dir=str(tmp_path / "jobs"),
        max_workers=1,
    )


def _wait(client, job_id):
    deadline = time.time() + 5
    while time.time() < deadline:
        row = client.get(f"/api/jobs/{job_id}").json()
        if row["status"] in {"completed", "failed"}:
            return row
        time.sleep(0.02)
    return row


def test_web_app_serves_ui_and_background_batch_download(tmp_path):
    config = _config(tmp_path)
    manager = JobManager(config.jobs_dir, max_workers=1)

    def fake_batch(_config, payload, _job_id, update, job_dir):
        assert payload["format_ids"] == ["fmt/18", "fmt/19"]
        update(progress=60, message="Assessing")
        (job_dir / "risk-report.csv").write_text("puid\nfmt/18\nfmt/19\n", encoding="utf-8")
        return {
            "message": "Complete",
            "downloads": {"csv": "risk-report.csv"},
            "preview": {"kind": "batch", "rows": [], "input_count": 2},
        }

    app = create_app(config, manager=manager, batch_runner=fake_batch)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert "QNL Preservation Risk Manager" in client.get("/").text
        assert client.get("/api/health").json() == {"status": "ok"}

        submitted = client.post(
            "/api/jobs/batch",
            json={"ids_text": "fmt/18\n[fmt 19]", "ai_mode": "off", "scope": "global"},
        )
        assert submitted.status_code == 200
        job = _wait(client, submitted.json()["job_id"])
        assert job["status"] == "completed"
        assert job["progress"] == 100
        download = client.get(f"/api/jobs/{job['job_id']}/download/csv")
        assert download.status_code == 200
        assert "fmt/18" in download.text

    manager.shutdown(wait=True)
