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
    ai.write_text('{"provider":"mock","human_format_assessment_limit":10}', encoding="utf-8")
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


def test_web_app_serves_curator_workflows_lookup_and_background_batch_download(tmp_path):
    config = _config(tmp_path)
    manager = JobManager(config.jobs_dir, max_workers=1)
    seen_modes = []

    def fake_batch(_config, payload, _job_id, update, job_dir):
        assert payload["format_ids"] == ["fmt/18", "fmt/19"]
        seen_modes.append(payload["ai_mode"])
        update(progress=60, message="Assessing")
        (job_dir / "risk-report.csv").write_text("puid\nfmt/18\nfmt/19\n", encoding="utf-8")
        (job_dir / "risk-report.html").write_text("<h1>Governed risk</h1>", encoding="utf-8")
        return {
            "message": "Complete",
            "downloads": {"csv": "risk-report.csv", "html": "risk-report.html"},
            "preview": {"kind": "batch", "rows": [], "input_count": 2},
        }

    def fake_lookup(_config, query, *, limit):
        assert query == "PDF"
        assert limit == 10
        return {
            "query": query,
            "match_count": 12,
            "returned_count": 10,
            "limit": 10,
            "limit_applied": True,
            "matches": [
                {
                    "puid": "fmt/276",
                    "puids": ["fmt/276"],
                    "canonical_id": "puid-fmt-276",
                    "label": "Acrobat PDF 1.7",
                    "version": "1.7",
                    "extensions": ["pdf"],
                    "mime_types": ["application/pdf"],
                    "loc_ids": [],
                    "nara_ids": [],
                }
            ],
        }

    app = create_app(config, manager=manager, batch_runner=fake_batch, lookup_runner=fake_lookup)
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "QNL Preservation Risk Manager" in home.text
        assert "Ask Risk" in home.text
        assert "PUID Lookup" in home.text
        assert "Run Report" in home.text
        assert "AI-assisted overall synthesis" in home.text
        assert "Governed risk" in home.text
        assert client.get("/api/health").json() == {"status": "ok"}

        lookup = client.get("/api/formats/lookup", params={"q": "PDF"})
        assert lookup.status_code == 200
        assert lookup.json()["match_count"] == 12
        assert lookup.json()["matches"][0]["puid"] == "fmt/276"

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
        html_download = client.get(f"/api/jobs/{job['job_id']}/download/html")
        assert html_download.status_code == 200
        assert html_download.headers["content-type"].startswith("text/html")

        synth = client.post(
            "/api/jobs/batch",
            json={"ids_text": "fmt/18\nfmt/19", "ai_mode": "synthesize", "scope": "global"},
        )
        assert synth.status_code == 200
        synth_job = _wait(client, synth.json()["job_id"])
        assert synth_job["status"] == "completed"

    assert seen_modes == ["off", "synthesize"]
