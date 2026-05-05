import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.projects import router as projects_router
from app.repositories import artifact_repository, project_repository
from app.services import auth_store, job_history


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    app = FastAPI()
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(projects_router, prefix='/api/v1')
    return TestClient(app)


def test_project_results_overview_and_workspace_file(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Alice', 'alice@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}

    project = project_repository.create_project(user.email, 'Demo', 'fast')
    script_dir = Path(tmp_path / 'workspace' / 'scripts')
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'demo_movie_story.json'
    highlights_path = script_dir / 'demo_movie_story_highlights.json'
    audit_path = script_dir / 'demo_movie_story_audit.json'
    script_payload = [{'id': 's1', 'timestamp': '00:00:01,000-00:00:05,000', 'narration': '旁白一'}]
    highlights_payload = [{'highlight_id': 'h1', 'highlight_rank': 1}]
    audit_payload = {'global_summary': {'story_summary': '这是摘要'}}
    script_path.write_text(json.dumps(script_payload, ensure_ascii=False), encoding='utf-8')
    highlights_path.write_text(json.dumps(highlights_payload, ensure_ascii=False), encoding='utf-8')
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False), encoding='utf-8')

    job_history.record_job(
        owner=user.email,
        project_id=project['id'],
        task_id='task-1',
        job_type='movie_story_script',
        task_dir=str(tmp_path / 'workspace' / 'tasks' / 'task-1'),
        created_at=now,
    )
    artifact_repository.upsert_artifact(
        owner_email=user.email,
        project_id=project['id'],
        task_id='task-1',
        artifact_type='script',
        path=str(script_path),
        label='解说脚本',
    )
    artifact_repository.upsert_artifact(
        owner_email=user.email,
        project_id=project['id'],
        task_id='task-1',
        artifact_type='highlights',
        path=str(highlights_path),
        label='高光列表',
    )
    artifact_repository.upsert_artifact(
        owner_email=user.email,
        project_id=project['id'],
        task_id='task-1',
        artifact_type='audit',
        path=str(audit_path),
        label='审计结果',
    )

    resp = client.get(f"/api/v1/projects/{project['id']}/results/overview", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['project_id'] == project['id']
    assert payload['latest_job']['project_id'] == project['id']
    assert payload['script_items'][0]['narration'] == '旁白一'
    assert payload['highlights'][0]['highlight_id'] == 'h1'
    assert payload['global_summary']['story_summary'] == '这是摘要'

    file_resp = client.get('/api/v1/projects/workspace-file', params={'path': str(script_path), 'project_id': project['id']}, headers=headers)
    assert file_resp.status_code == 200
    assert '旁白一' in file_resp.text


def test_workspace_file_requires_artifact_registration(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Bob', 'bob@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}
    project = project_repository.create_project(user.email, 'Demo', 'fast')

    script_dir = Path(tmp_path / 'workspace' / 'scripts')
    script_dir.mkdir(parents=True, exist_ok=True)
    hidden_path = script_dir / 'hidden.txt'
    hidden_path.write_text('do-not-read', encoding='utf-8')

    resp = client.get(
        '/api/v1/projects/workspace-file',
        params={'path': str(hidden_path), 'project_id': project['id']},
        headers=headers,
    )
    assert resp.status_code == 404
