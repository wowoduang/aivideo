from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.jobs import router as jobs_router
from app.services import auth_store, job_history, usage_meter


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    return TestClient(app)


def _headers(email: str = "alice@example.com") -> dict[str, str]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        user = auth_store.register_user("Alice", email, "secret123", now)
    except ValueError:
        user = auth_store.get_user(email)
    token = auth_store.create_session(user.email, now)
    return {"Authorization": f"Bearer {token}"}


def test_rq_worker_status_degrades_without_optional_dependencies(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_JOB_BACKEND", "rq")
    client = _client(tmp_path, monkeypatch)
    headers = _headers()

    resp = client.get("/api/v1/jobs/workers/status", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["backend"] == "rq"
    assert payload["queue"] == "aivideo_jobs"
    assert "available" in payload


def test_rq_snapshot_reads_persisted_job_history(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("AIVIDEO_JOB_BACKEND", "rq")
    _headers("alice@example.com")
    job_history.record_job(
        owner="alice@example.com",
        task_id="rq-history-task",
        project_id="",
        job_type="subtitle",
        task_dir="/tmp/rq-history-task",
        status="queued",
        progress=0,
        message="queued:rqueue",
    )

    from app.services.job_runner import runner_api

    snapshot = runner_api()["get_task_snapshot"]("rq-history-task")
    assert snapshot is not None
    assert snapshot["queue_backend"] == "rq"
    assert snapshot["status"] == "queued"


def test_provider_level_usage_records_tokens_tts_and_asr(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    _headers("alice@example.com")

    usage_meter.record_llm_usage(
        owner="alice@example.com",
        provider="https://api.openai.com/v1",
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        task_id="task-1",
        project_id="project-1",
        label="unit",
    )
    usage_meter.record_tts_usage(
        owner="alice@example.com",
        provider="edge_tts",
        voice_name="zh-CN-XiaoxiaoNeural-Female",
        characters=12,
        audio_bytes=1234,
        audio_seconds=3.2,
        task_id="task-1",
        project_id="project-1",
    )
    usage_meter.record_asr_usage(
        owner="alice@example.com",
        provider="qwen3-asr-flash",
        model="qwen3-asr-flash",
        audio_seconds=61.0,
        task_id="task-1",
        project_id="project-1",
    )

    summary = usage_meter.summarize_usage("alice@example.com")
    rows = {(row["event_type"], row["provider"], row["unit_name"]): row for row in summary["summary"]}
    assert rows[("llm_prompt_tokens", "openai", "tokens")]["total_units"] == 10
    assert rows[("llm_completion_tokens", "openai", "tokens")]["total_units"] == 20
    assert rows[("llm_total_tokens", "openai", "tokens")]["total_units"] == 30
    assert rows[("tts_characters", "edge_tts", "characters")]["total_units"] == 12
    assert rows[("tts_audio_seconds", "edge_tts", "seconds")]["total_units"] == 3
    assert rows[("asr_audio_seconds", "dashscope", "seconds")]["total_units"] == 61
