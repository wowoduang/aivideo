import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.narration import router as narration_router
from app.repositories import artifact_repository, project_repository
from app.services import auth_store


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    app = FastAPI()
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(narration_router, prefix='/api/v1')
    return TestClient(app)


def test_highlight_selection_round_trip_uses_artifacts(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Alice', 'alice@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}
    project = project_repository.create_project(user.email, 'Movie Demo', 'fast')

    out_dir = Path(tmp_path / 'workspace' / 'results')
    out_dir.mkdir(parents=True, exist_ok=True)
    highlights_path = out_dir / 'highlights.json'
    highlights_payload = [
        {
            'highlight_id': 'h1',
            'video_start': 10,
            'video_end': 22,
            'summary': '男主发现门后有人。',
            'selection_reasons': ['冲突开始', '悬疑感强'],
            'scores': {'story_score': 0.86},
        },
        {
            'highlight_id': 'h2',
            'video_start': 30,
            'video_end': 44,
            'subtitle_text': '两人开始争吵。',
            'highlight_score': 0.72,
        },
    ]
    highlights_path.write_text(json.dumps(highlights_payload, ensure_ascii=False), encoding='utf-8')
    artifact_repository.upsert_artifact(
        owner_email=user.email,
        project_id=project['id'],
        task_id='',
        artifact_type='highlights',
        path=str(highlights_path),
        label='高光列表',
    )

    resp = client.get(f"/api/v1/projects/{project['id']}/narration/highlights/selection", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['source'] == 'generated'
    assert payload['total_count'] == 2
    assert payload['items'][0]['id'] == 'h1'
    assert payload['items'][0]['selection_reasons'] == ['冲突开始', '悬疑感强']
    assert payload['selected_duration_sec'] == 26

    items = payload['items']
    items[1]['selected'] = False
    items[0]['locked'] = True
    save_resp = client.post(
        f"/api/v1/projects/{project['id']}/narration/highlights/selection",
        headers=headers,
        json={'items': items, 'note': '人工排除第二段'},
    )
    assert save_resp.status_code == 200
    saved = save_resp.json()
    assert saved['artifact']['artifact_type'] == 'highlight_selection'
    assert saved['selection']['selected_count'] == 1
    assert saved['selection']['selected_duration_sec'] == 12

    reread = client.get(f"/api/v1/projects/{project['id']}/narration/highlights/selection", headers=headers)
    assert reread.status_code == 200
    reread_payload = reread.json()
    assert reread_payload['source'] == 'saved'
    assert reread_payload['items'][1]['selected'] is False
    assert reread_payload['items'][0]['locked'] is True
