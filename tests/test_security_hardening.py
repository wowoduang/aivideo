from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.services import auth_store, metadata_db


def test_session_tokens_are_hashed_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user("Alice", "alice@example.com", "secret123", now)

    token = auth_store.create_session(user.email, now)

    raw = metadata_db.fetch_one("SELECT token FROM user_sessions WHERE token = ?", (token,))
    assert raw is None
    rows = metadata_db.fetch_all("SELECT token FROM user_sessions")
    assert len(rows) == 1
    assert str(rows[0]["token"]).startswith("sha256:")
    assert auth_store.get_user_by_token(token).email == "alice@example.com"


def test_uploaded_media_requires_bearer_or_access_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.delenv("AIVIDEO_PUBLIC_UPLOADS", raising=False)
    app = create_app()
    client = TestClient(app)

    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user("Bob", "bob@example.com", "secret123", now)
    token = auth_store.create_session(user.email, now)

    media_dir = tmp_path / "workspace" / "frontend_uploads" / "video"
    media_dir.mkdir(parents=True, exist_ok=True)
    media_path = media_dir / "demo.mp4"
    media_path.write_bytes(b"fake-mp4")

    assert client.get("/uploads/video/demo.mp4").status_code == 401
    assert client.get(f"/uploads/video/demo.mp4?access_token={token}").status_code == 200
    assert client.get(
        "/uploads/video/demo.mp4",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200


def test_signed_upload_url_allows_access_without_raw_session_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.delenv("AIVIDEO_PUBLIC_UPLOADS", raising=False)
    app = create_app()
    client = TestClient(app)

    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user("Cara", "cara@example.com", "secret123", now)
    token = auth_store.create_session(user.email, now)

    response = client.post(
        "/api/v1/uploads/subtitle",
        files={"file": ("demo.srt", b"1\n00:00:00,000 --> 00:00:01,000\nhello\n", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token=" not in payload["url"]
    assert "signature=" in payload["url"]
    assert client.get(payload["url"]).status_code == 200


def test_local_job_cancel_marks_pending_job_cancel_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    from app.models import const
    from app.services import state as sm
    from app.services import local_job_runner
    from app.utils import utils

    now = datetime.now(timezone.utc).isoformat()
    auth_store.register_user("Cancel", "cancel@example.com", "secret123", now)

    task_id = "cancel-me"
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=10,
        job_type="subtitle",
        status="processing",
        message="running",
        task_dir=utils.task_dir(task_id),
        owner_email="cancel@example.com",
        project_id="",
    )

    assert local_job_runner.request_job_cancel(task_id) is True
    snapshot = local_job_runner.get_task_snapshot(task_id)
    assert snapshot["status"] in {"cancel_requested", "cancelled"}
