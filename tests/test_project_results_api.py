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
    understanding_path = script_dir / 'demo_movie_story_understanding_script.json'
    script_payload = [{'id': 's1', 'timestamp': '00:00:01,000-00:00:05,000', 'narration': '旁白一'}]
    highlights_payload = [{'highlight_id': 'h1', 'highlight_rank': 1}]
    audit_payload = {'global_summary': {'story_summary': '这是摘要'}}
    script_path.write_text(json.dumps(script_payload, ensure_ascii=False), encoding='utf-8')
    highlights_path.write_text(json.dumps(highlights_payload, ensure_ascii=False), encoding='utf-8')
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False), encoding='utf-8')
    understanding_path.write_text(json.dumps({
        'artifact': 'movie_story_understanding_script',
        'global_story_understanding': {'main_storyline': 'whole story', 'story_summary': 'è¿™æ˜¯æ‘˜è¦'},
        'segment_understandings': [
            {
                'segment_id': 's1',
                'local_understanding': {'core_event': 'segment understanding'},
                'legacy_segment_understanding': {'shot_role': 'dialogue_exchange'},
            }
        ],
    }, ensure_ascii=False), encoding='utf-8')

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

    artifact_repository.upsert_artifact(
        owner_email=user.email,
        project_id=project['id'],
        task_id='task-1',
        artifact_type='understanding_script',
        path=str(understanding_path),
        label='understanding script',
    )

    resp = client.get(f"/api/v1/projects/{project['id']}/results/overview", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['project_id'] == project['id']
    assert payload['latest_job']['project_id'] == project['id']
    assert payload['script_items'][0]['narration'] == '旁白一'
    assert payload['highlights'][0]['highlight_id'] == 'h1'
    assert payload['global_summary']['story_summary'] == '这是摘要'

    assert payload['understanding_script']['artifact'] == 'movie_story_understanding_script'
    assert payload['segment_understandings'][0]['local_understanding']['core_event'] == 'segment understanding'

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


def test_project_api_accepts_generated_backend_script_items(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Cara', 'cara@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}
    project = project_repository.create_project(user.email, 'Movie Script', 'fast')
    generated_items = [
        {
            '_id': 8,
            'timestamp': '00:02:59,360-00:03:06,080',
            'picture': 'plot_008_01_182.720.jpg',
            'narration': '朝廷的钱粮已经见底，可宫里还在惦记排场。',
            'OST': 2,
            'evidence_refs': ['plot_008'],
            'local_understanding': {'core_event': 'tax pressure reaches village'},
        }
    ]
    project_repository.update_project(
        user.email,
        project['id'],
        {'status': 'failed', 'currentStep': 'generate', 'scriptItems': generated_items},
    )

    list_resp = client.get('/api/v1/projects', headers=headers)
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload['items'][0]['scriptItems'][0]['_id'] == 8

    item_resp = client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    assert item_resp.status_code == 200
    assert item_resp.json()['item']['scriptItems'][0]['local_understanding']['core_event'] == 'tax pressure reaches village'
