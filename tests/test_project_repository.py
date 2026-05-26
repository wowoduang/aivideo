from datetime import datetime, timezone

from app.repositories import project_repository
from app.services import auth_store


def test_project_repository_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    auth_store.register_user('Alice', 'alice@example.com', 'secret123', datetime.now(timezone.utc).isoformat())
    created = project_repository.create_project('alice@example.com', 'Demo', 'fast')
    assert created['name'] == 'Demo'
    updated = project_repository.update_project('alice@example.com', created['id'], {'status': 'completed'})
    assert updated['status'] == 'completed'
    assert len(project_repository.list_projects('alice@example.com')) == 1
    assert project_repository.delete_project('alice@example.com', created['id']) is True
    assert project_repository.list_projects('alice@example.com') == []
