from fastapi.testclient import TestClient


def test_app_starts_without_optional_llm_and_tts_dependencies():
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
    assert voices.status_code == 503
    assert voices.json()['detail'].startswith('missing_optional_dependency:')
