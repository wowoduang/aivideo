from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.system import router as system_router
from app.repositories import project_repository
from app.services import auth_store, job_history, runtime_context, usage_meter


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    return TestClient(app)


def _auth_headers(email: str = "alice@example.com") -> dict[str, str]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        user = auth_store.register_user("Alice", email, "secret123", now)
    except ValueError:
        user = auth_store.get_user(email)
    token = auth_store.create_session(user.email, now)
    return {"Authorization": f"Bearer {token}"}


def test_jobs_list_and_worker_status_are_authenticated(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _auth_headers()
    project = project_repository.create_project("alice@example.com", "Demo", "fast")
    job_history.record_job(
        owner="alice@example.com",
        project_id=project["id"],
        task_id="task-1",
        job_type="movie_story_script",
        task_dir="/tmp/task-1",
        status="queued",
        progress=0,
        message="queued",
    )

    unauth = client.get("/api/v1/jobs")
    assert unauth.status_code == 401

    resp = client.get("/api/v1/jobs", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    assert payload["items"][0]["task_id"] == "task-1"

    worker_resp = client.get("/api/v1/jobs/workers/status", headers=headers)
    assert worker_resp.status_code == 200
    worker = worker_resp.json()
    assert worker["backend"] == "threadpool"
    assert worker["max_workers"] >= 1


def test_llm_usage_is_recorded_from_runtime_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    _auth_headers("alice@example.com")
    with runtime_context.job_context(owner="alice@example.com", task_id="task-llm", project_id="project-1"):
        usage_meter.record_llm_usage(
            owner=runtime_context.current_owner(),
            provider="unit-test",
            model="fake-model",
            prompt_chars=12,
            completion_chars=34,
            task_id=runtime_context.current_task_id(),
            project_id=runtime_context.current_project_id(),
            label="unit",
        )

    summary = usage_meter.summarize_usage("alice@example.com")
    rows = {(row["event_type"], row["provider"]): row for row in summary["summary"]}
    assert rows[("llm_prompt", "unit-test")]["total_units"] == 12
    assert rows[("llm_completion", "unit-test")]["total_units"] == 34

    recent = summary["recent"]
    assert any(item["metadata"].get("task_id") == "task-llm" for item in recent)


def test_job_events_are_recorded_and_owner_scoped(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _auth_headers("alice@example.com")
    project = project_repository.create_project("alice@example.com", "Events Demo", "fast")

    from app.services.local_job_runner import _start_job_thread

    def runner():
        return {"success": True, "result": {"ok": True}}

    task_id = _start_job_thread(
        task_id="event-task-1",
        job_type="movie_story_script",
        runner=runner,
        owner_email="alice@example.com",
        project_id=project["id"],
    )

    import time
    for _ in range(40):
        history = job_history.get_job(task_id)
        if history and history["status"] == "complete":
            break
        time.sleep(0.05)

    resp = client.get(f"/api/v1/jobs/{task_id}/events", headers=headers)
    assert resp.status_code == 200
    events = resp.json()["items"]
    event_types = [item["event_type"] for item in events]
    assert "queued" in event_types
    assert "running" in event_types
    assert "complete" in event_types
    assert all(item["task_id"] == task_id for item in events)

    bob_headers = _auth_headers("bob@example.com")
    denied = client.get(f"/api/v1/jobs/{task_id}/events", headers=bob_headers)
    assert denied.status_code == 404
