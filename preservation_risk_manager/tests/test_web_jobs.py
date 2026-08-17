import time

from preservation_risk_manager.web_jobs import JobManager


def test_job_manager_runs_background_job_and_exposes_artifact(tmp_path):
    manager = JobManager(tmp_path, max_workers=1)

    def runner(job_id, update, job_dir):
        update(progress=40, message="Working")
        (job_dir / "result.txt").write_text("done", encoding="utf-8")
        return {
            "message": "Complete",
            "preview": {"kind": "human", "text": "done"},
            "downloads": {"text": "result.txt"},
        }

    submitted = manager.submit("human", runner)
    deadline = time.time() + 5
    current = submitted
    while time.time() < deadline:
        current = manager.get(submitted["job_id"])
        if current["status"] in {"completed", "failed"}:
            break
        time.sleep(0.02)

    assert current["status"] == "completed"
    assert current["progress"] == 100
    assert current["preview"]["text"] == "done"
    assert manager.artifact_path(submitted["job_id"], "text").read_text(encoding="utf-8") == "done"
    assert (tmp_path / submitted["job_id"] / "job.json").is_file()
    manager.shutdown(wait=True)
