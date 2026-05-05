from datetime import datetime, timezone

from app.services import auth_store


def test_register_change_and_login(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    now = datetime.now(timezone.utc).isoformat()
    auth_store.register_user('Alice', 'alice@example.com', 'secret123', now)
    assert auth_store.authenticate('alice@example.com', 'secret123') is not None
    auth_store.change_password('alice@example.com', 'secret123', 'newsecret123')
    assert auth_store.authenticate('alice@example.com', 'secret123') is None
    assert auth_store.authenticate('alice@example.com', 'newsecret123') is not None


def test_forgot_and_reset(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    now = datetime.now(timezone.utc).isoformat()
    auth_store.register_user('Bob', 'bob@example.com', 'secret123', now)
    record = auth_store.issue_password_reset('bob@example.com', now)
    assert record is not None
    assert auth_store.consume_password_reset(record.token, 'changed123') is not None
    assert auth_store.authenticate('bob@example.com', 'changed123') is not None


def test_bootstrap_default_user(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    monkeypatch.setenv('AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN', '1')
    monkeypatch.setenv('AIVIDEO_BOOTSTRAP_EMAIL', 'demo@aivideo.local')
    monkeypatch.setenv('AIVIDEO_BOOTSTRAP_PASSWORD', '12345678')
    user = auth_store.ensure_bootstrap_user()
    assert user is not None
    assert auth_store.authenticate('demo@aivideo.local', '12345678') is not None
