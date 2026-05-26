from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.auth import router as auth_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.projects import router as projects_router
from app.repositories import artifact_repository, project_repository
from app.services import auth_store, job_history


def create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVIDEO_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    return TestClient(app)


def test_jobs_require_authentication(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    resp = client.post('/api/v1/jobs/subtitle', json={'request': {'video_path': '/tmp/demo.mp4'}})
    assert resp.status_code == 401
    assert resp.json()['detail'] == 'missing_token'


def test_job_completion_is_persisted_without_polling(tmp_path, monkeypatch):
    client = create_client(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    user = auth_store.register_user('Alice', 'alice@example.com', 'secret123', now)
    token = auth_store.create_session(user.email, now)
    headers = {'Authorization': f'Bearer {token}'}
    project = project_repository.create_project(user.email, 'Demo', 'fast')

    script_dir = tmp_path / 'workspace' / 'scripts'
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'demo_movie_story.json'
    script_path.write_text('[]', encoding='utf-8')

    def fake_start_local_movie_story_script_job(*, request, task_id, owner_email='', project_id=''):
        from app.services.local_job_runner import _mark_job_complete, _start_job_thread

        def runner():
            return {
                'success': True,
                'script_path': str(script_path),
                'script_items': [{'id': 's1', 'narration': 'hi'}],
            }

        return _start_job_thread(
            task_id=task_id,
            job_type='movie_story_script',
            runner=runner,
            owner_email=owner_email,
            project_id=project_id,
        )

    monkeypatch.setattr('app.api.routers.jobs._runner_api', lambda: {
        'get_task_snapshot': lambda task_id: __import__('app.services.local_job_runner', fromlist=['get_task_snapshot']).get_task_snapshot(task_id),
        'start_local_highlight_script_job': lambda **kwargs: 'unused-highlight',
        'start_local_movie_story_script_job': fake_start_local_movie_story_script_job,
        'start_local_subtitle_job': lambda **kwargs: 'unused-subtitle',
        'start_local_video_job': lambda **kwargs: 'unused-video',
    })

    resp = client.post(
        '/api/v1/jobs/movie-story-script',
        json={'project_id': project['id'], 'request': {'video_path': '/tmp/demo.mp4'}},
        headers=headers,
    )
    assert resp.status_code == 202
    task_id = resp.json()['task_id']

    # allow background thread to finish
    import time
    for _ in range(30):
        job = job_history.get_job(task_id)
        if job and job['status'] == 'complete':
            break
        time.sleep(0.05)

    job = job_history.get_job(task_id)
    assert job is not None
    assert job['status'] == 'complete'
    artifacts = artifact_repository.list_project_artifacts(project['id'])
    assert any(item['artifact_type'] == 'script' for item in artifacts)
    refreshed = project_repository.get_project(user.email, project['id'])
    assert refreshed['status'] == 'completed'
