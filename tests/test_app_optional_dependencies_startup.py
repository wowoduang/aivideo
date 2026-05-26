from fastapi.testclient import TestClient


def test_app_starts_without_optional_llm_and_tts_dependencies(tmp_path, monkeypatch):
    # Startup smoke test must not read a developer workspace that may already
    # contain users or optional TTS configuration.
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN", "1")
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_EMAIL", "demo@aivideo.local")
    monkeypatch.setenv("AIVIDEO_BOOTSTRAP_PASSWORD", "12345678")
    monkeypatch.setenv("AIVIDEO_EXPOSE_BOOTSTRAP_PASSWORD", "0")

    from app.api.main import create_app

    client = TestClient(create_app())

    cfg = client.get('/api/config')
    assert cfg.status_code == 200

    status = client.get('/api/v1/auth/status')
    assert status.status_code == 200
    payload = status.json()
    assert payload['bootstrap_enabled'] is True
    assert payload['bootstrap_email'] == 'demo@aivideo.local'

    voices = client.get('/api/v1/tts/voices')
    assert voices.status_code in {200, 503}
    if voices.status_code == 503:
        assert voices.json()['detail'].startswith('missing_optional_dependency:')
