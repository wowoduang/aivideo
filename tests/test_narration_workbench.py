import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.narration import router as narration_router
from app.repositories import artifact_repository, project_repository
from app.services import auth_store
from app.services.narration_quality import build_quality_report, humanize_script_segments, normalize_script_segments


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv('AIVIDEO_WORKSPACE_ROOT', str(tmp_path / 'workspace'))
    app = FastAPI()
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(narration_router, prefix='/api/v1')
    return TestClient(app)


def test_narration_quality_scores_and_humanize_are_complete():
    script = [
        {
            'id': 's1',
            'timestamp': '00:00:01,000-00:00:06,000',
            'originalSubtitle': '男主走进地下室，听到门后有声音。',
            'narration': '首先，男主进入地下室后，发现了一个异常现象，这使他感到非常紧张。',
        }
    ]
    segments = normalize_script_segments(script)
    assert segments[0]['start'] == 1
    assert segments[0]['end'] == 6
    assert segments[0]['role'] == 'summary'

    report = build_quality_report(script_items=script)
    assert report['summary']['segment_count'] == 1
    assert report['summary']['overall_score'] > 0
    assert report['segments'][0]['estimated_tts_duration_sec'] > 0
    assert report['segments'][0]['issues']

    humanized = humanize_script_segments(script, persona='suspense')
    assert humanized['persona_label'] == '悬疑紧张'
    assert humanized['changes']
    assert '异常现象' not in humanized['script_items'][0]['narration']
    assert humanized['script_items'][0]['prosody']['speed'] > 0
    assert humanized['quality_report']['summary']['segment_count'] == 1


def test_narration_workbench_api_uses_project_artifacts_and_saves_versions(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Alice', 'alice@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}
    project = project_repository.create_project(user.email, 'Movie Demo', 'fast')

    script_dir = Path(tmp_path / 'workspace' / 'scripts')
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'script.json'
    highlights_path = script_dir / 'highlights.json'
    script_payload = [
        {
            'id': 's1',
            'timestamp': '00:00:02,000-00:00:07,000',
            'original_subtitle': '女人发现抽屉里的照片。',
            'narration': '女人打开抽屉，发现照片不见了。',
        }
    ]
    highlights_payload = [{'highlight_id': 'h1', 'start': 2, 'end': 7, 'subtitle_text': '女人发现抽屉里的照片。'}]
    script_path.write_text(json.dumps(script_payload, ensure_ascii=False), encoding='utf-8')
    highlights_path.write_text(json.dumps(highlights_payload, ensure_ascii=False), encoding='utf-8')
    artifact_repository.upsert_artifact(owner_email=user.email, project_id=project['id'], task_id='', artifact_type='script', path=str(script_path), label='解说脚本')
    artifact_repository.upsert_artifact(owner_email=user.email, project_id=project['id'], task_id='', artifact_type='highlights', path=str(highlights_path), label='高光列表')

    resp = client.get(f"/api/v1/projects/{project['id']}/narration/workbench", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['script_segments'][0]['narration'] == '女人打开抽屉，发现照片不见了。'
    assert payload['evidence_pack']
    assert payload['quality_report']['summary']['segment_count'] == 1
    assert payload['timeline_blocks'][0]['evidence_support_score'] >= 0

    q_resp = client.post(f"/api/v1/projects/{project['id']}/narration/quality-report", headers=headers, json={'script_items': script_payload, 'save_report': True})
    assert q_resp.status_code == 200
    assert q_resp.json()['summary']['segment_count'] == 1

    h_resp = client.post(f"/api/v1/projects/{project['id']}/narration/humanize", headers=headers, json={'script_items': script_payload, 'persona': 'documentary', 'save_version': True})
    assert h_resp.status_code == 200
    assert h_resp.json()['artifact']['artifact_type'] == 'script_version'

    versions = client.get(f"/api/v1/projects/{project['id']}/narration/scripts/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()['items']) == 1
