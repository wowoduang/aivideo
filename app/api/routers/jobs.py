from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas.jobs import (
    HighlightJobCreateRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    MovieStoryJobCreateRequest,
    SubtitleJobCreateRequest,
    VideoJobCreateRequest,
)
from app.repositories import artifact_repository, project_repository
from app.services import auth_store, job_history
from app.utils import utils


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _runner_api():
    try:
        from app.services.local_job_runner import (
            get_task_snapshot,
            start_local_highlight_script_job,
            start_local_movie_story_script_job,
            start_local_subtitle_job,
            start_local_video_job,
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"missing_optional_dependency:{exc.name}") from exc

    return {
        "get_task_snapshot": get_task_snapshot,
        "start_local_highlight_script_job": start_local_highlight_script_job,
        "start_local_movie_story_script_job": start_local_movie_story_script_job,
        "start_local_subtitle_job": start_local_subtitle_job,
        "start_local_video_job": start_local_video_job,
    }


def _accepted_response(task_id: str) -> JobAcceptedResponse:
    snapshot = _runner_api()["get_task_snapshot"](task_id)
    if not snapshot:
        raise HTTPException(status_code=500, detail="job_created_but_state_missing")
    return JobAcceptedResponse(
        task_id=task_id,
        job_type=str(snapshot.get("job_type", "video")),
        status=str(snapshot.get("status", "processing")),
        progress=int(snapshot.get("progress", 0) or 0),
        task_dir=str(snapshot.get("task_dir", "")),
    )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _require_user(authorization: Optional[str]):
    if not authorization:
        raise HTTPException(status_code=401, detail="missing_token")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid_token")
    token = authorization.split(" ", 1)[1].strip()
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user


def _record_history(*, email: str, task_id: str, job_type: str, project_id: str = "") -> None:
    job_history.record_job(
        owner=email,
        project_id=project_id,
        task_id=task_id,
        job_type=job_type,
        task_dir=str(utils.task_dir(task_id)),
        status="processing",
        progress=0,
        message="queued",
        error="",
        created_at=_now_iso(),
    )


def _try_update_project_on_submit(owner_email: Optional[str], project_id: str) -> None:
    # currentStep 是前端页面停留位置，不由后端任务提交来改。
    # 否则字幕任务一提交就会把页面推到 generate。
    return



def _try_update_project_on_complete(owner_email: Optional[str], project_id: str, result_payload: dict[str, Any]) -> None:
    if not owner_email or not project_id:
        return
    patch: dict[str, Any] = {"status": "completed"}
    script_items = result_payload.get("script_items")
    if isinstance(script_items, list) and script_items:
        patch["scriptItems"] = script_items
    project_repository.update_project(owner_email, project_id, patch)



@router.post("/video", response_model=JobAcceptedResponse, status_code=202)
def create_video_job(payload: VideoJobCreateRequest, authorization: Optional[str] = Header(default=None)):
    user = _require_user(authorization)
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    task_id = str(payload.task_id or uuid4())
    _record_history(email=user.email, task_id=task_id, job_type="video", project_id=payload.project_id)
    task_id = _runner_api()["start_local_video_job"](
        params=payload.params,
        task_id=task_id,
        owner_email=user.email,
        project_id=payload.project_id,
    )
    _try_update_project_on_submit(user.email, payload.project_id)
    return _accepted_response(task_id)


@router.post("/highlight-script", response_model=JobAcceptedResponse, status_code=202)
def create_highlight_script_job(
    payload: HighlightJobCreateRequest, authorization: Optional[str] = Header(default=None)
):
    user = _require_user(authorization)
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    task_id = str(payload.task_id or uuid4())
    _record_history(email=user.email, task_id=task_id, job_type="highlight_script", project_id=payload.project_id)
    task_id = _runner_api()["start_local_highlight_script_job"](
        request=payload.request.model_dump(),
        task_id=task_id,
        owner_email=user.email,
        project_id=payload.project_id,
    )
    _try_update_project_on_submit(user.email, payload.project_id)
    return _accepted_response(task_id)


@router.post("/movie-story-script", response_model=JobAcceptedResponse, status_code=202)
def create_movie_story_script_job(
    payload: MovieStoryJobCreateRequest, authorization: Optional[str] = Header(default=None)
):
    user = _require_user(authorization)
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    task_id = str(payload.task_id or uuid4())
    _record_history(email=user.email, task_id=task_id, job_type="movie_story_script", project_id=payload.project_id)
    task_id = _runner_api()["start_local_movie_story_script_job"](
        request=payload.request.model_dump(),
        task_id=task_id,
        owner_email=user.email,
        project_id=payload.project_id,
    )
    _try_update_project_on_submit(user.email, payload.project_id)
    return _accepted_response(task_id)


@router.post("/subtitle", response_model=JobAcceptedResponse, status_code=202)
def create_subtitle_job(
    payload: SubtitleJobCreateRequest, authorization: Optional[str] = Header(default=None)
):
    user = _require_user(authorization)
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    task_id = str(payload.task_id or uuid4())
    _record_history(email=user.email, task_id=task_id, job_type="subtitle", project_id=payload.project_id)
    task_id = _runner_api()["start_local_subtitle_job"](
        request=payload.request.model_dump(),
        task_id=task_id,
        owner_email=user.email,
        project_id=payload.project_id,
    )
    _try_update_project_on_submit(user.email, payload.project_id)
    return _accepted_response(task_id)


@router.get("/{task_id}", response_model=JobStatusResponse)
def get_job_status(task_id: str):
    snapshot = _runner_api()["get_task_snapshot"](task_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="task_not_found")

    payload = dict(snapshot)
    return JobStatusResponse(
        task_id=task_id,
        job_type=str(payload.pop("job_type", "video")),
        status=str(payload.pop("status", "processing")),
        state=int(payload.pop("state", 0) or 0),
        progress=int(payload.pop("progress", 0) or 0),
        message=str(payload.get("message", "") or ""),
        error=str(payload.get("error", "") or ""),
        task_dir=str(payload.get("task_dir", "") or ""),
        videos=list(payload.get("videos", []) or []),
        combined_videos=list(payload.get("combined_videos", []) or []),
        is_running=bool(payload.pop("is_running", False)),
        payload=payload,
    )
