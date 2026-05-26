from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    return TestClient(app)


def test_auth_status_and_bootstrap_login(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN", "1")
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_EMAIL", "demo@aivideo.local")
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_PASSWORD", "12345678")
    client = create_client(tmp_path, monkeypatch)

    status = client.get("/api/v1/auth/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["has_users"] is False
    assert payload["bootstrap_email"] == "demo@aivideo.local"

    login = client.post("/api/v1/auth/login", json={"email": "demo@aivideo.local", "password": "12345678"})
    assert login.status_code == 200
    token = login.json()["token"]
    assert token

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "demo@aivideo.local"


def test_register_change_reset_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN", "0")
    client = create_client(tmp_path, monkeypatch)

    register = client.post("/api/v1/auth/register", json={"name": "Alice", "email": "alice@example.com", "password": "secret123"})
    assert register.status_code == 200
    token = register.json()["token"]

    change = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "secret123", "new_password": "newsecret123"},
    )
    assert change.status_code == 200

    relogin = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "newsecret123"})
    assert relogin.status_code == 200
    token = relogin.json()["token"]

    forgot = client.post("/api/v1/auth/forgot-password", json={"email": "alice@example.com"})
    assert forgot.status_code == 200
    reset_token = forgot.json()["reset_token"]
    assert reset_token

    reset = client.post("/api/v1/auth/reset-password", json={"token": reset_token, "password": "resetpass123"})
    assert reset.status_code == 200

    relogin2 = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "resetpass123"})
    assert relogin2.status_code == 200
    token2 = relogin2.json()["token"]

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token2}"})
    assert logout.status_code == 200
