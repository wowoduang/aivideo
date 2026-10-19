from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas.jobs import (
    HighlightJobCreateRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    JobCancelResponse,
    JobEventItem,
    JobEventListResponse,
    JobHistoryItem,
    JobListResponse,
    JobWorkerStatusResponse,
    MovieStoryJobCreateRequest,
    SubtitleJobCreateRequest,
    VideoJobCreateRequest,
)
from app.repositories import artifact_repository, project_repository
from app.services import auth_store, job_events, job_history
from app.models import const
from app.api.deps import assert_rate_limit, require_user
from app.utils import utils
from app.services.narration_text_sanitizer import sanitize_deliverable_narration_text


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _runner_api():
    try:
        from app.services.job_runner import runner_api

        return runner_api()
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"missing_optional_dependency:{exc.name}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


def _record_history(*, email: str, task_id: str, job_type: str, project_id: str = "") -> None:
    job_history.record_job(
        owner=email,
        project_id=project_id,
        task_id=task_id,
        job_type=job_type,
        task_dir=str(utils.task_dir(task_id)),
        status="queued",
        progress=0,
        message="queued",
        error="",
        created_at=_now_iso(),
    )


def _try_update_project_on_submit(owner_email: Optional[str], project_id: str) -> None:
    # currentStep 是前端页面停留位置，不由后端任务提交来改。
    # 否则字幕任务一提交就会把页面推到 generate。
    return


def _guard_job_submit(user: auth_store.StoredUser, job_type: str) -> None:
    # Prevent accidental UI double-clicks or API loops from enqueueing a large
    # number of expensive video/ASR/LLM jobs in the local runner.
    assert_rate_limit(user.email, f"job:{job_type}", limit=20, window_seconds=60)



def _try_update_project_on_complete(owner_email: Optional[str], project_id: str, result_payload: dict[str, Any]) -> None:
    if not owner_email or not project_id:
        return
    patch: dict[str, Any] = {"status": "completed"}
    script_items = result_payload.get("script_items")
    if isinstance(script_items, list) and script_items:
        patch["scriptItems"] = script_items
    project_repository.update_project(owner_email, project_id, patch)



@router.post("/video", response_model=JobAcceptedResponse, status_code=202)
def create_video_job(payload: VideoJobCreateRequest, user: auth_store.StoredUser = Depends(require_user)):
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    _guard_job_submit(user, "video")
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
    payload: HighlightJobCreateRequest, user: auth_store.StoredUser = Depends(require_user)
):
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    _guard_job_submit(user, "highlight_script")
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
    payload: MovieStoryJobCreateRequest, user: auth_store.StoredUser = Depends(require_user)
):
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    _guard_job_submit(user, "movie_story_script")
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
    payload: SubtitleJobCreateRequest, user: auth_store.StoredUser = Depends(require_user)
):
    if payload.project_id:
        item = project_repository.get_project(user.email, payload.project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
    _guard_job_submit(user, "subtitle")
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


def _state_from_status(status: str) -> int:
    if status == "complete":
        return const.TASK_STATE_COMPLETE
    if status in {"failed", "cancelled"}:
        return const.TASK_STATE_FAILED
    return const.TASK_STATE_PROCESSING


def _assert_job_owner(task_id: str, user_email: str, snapshot: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    history = job_history.get_job(task_id)
    owner = str((history or {}).get("owner") or (snapshot or {}).get("owner_email") or "").strip().lower()
    if owner and owner != str(user_email or "").strip().lower():
        # Avoid leaking whether another user's task id exists.
        raise HTTPException(status_code=404, detail="task_not_found")
    return history


def _load_movie_story_script_items_for_status(path: str) -> list[dict[str, Any]]:
    import json
    from pathlib import Path

    raw = str(path or "").strip()
    if not raw:
        return []
    candidates = []
    p = Path(raw)
    candidates.append(p)
    if not p.is_absolute():
        candidates.append(Path.cwd() / p)
    for file_path in candidates:
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            items = data.get("script_items") or data.get("items") or data.get("segments") or data.get("script")
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
    return []


def _normalize_movie_story_script_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    if str(data.get("job_type") or "") != "movie_story_script":
        return data

    result = data.get("result")
    if not isinstance(result, dict):
        result = {}
    else:
        result = dict(result)

    if not isinstance(result.get("script_items"), list) or not result.get("script_items"):
        top_items = data.get("script_items")
        if isinstance(top_items, list) and top_items:
            result["script_items"] = top_items

    if not isinstance(result.get("script_items"), list) or not result.get("script_items"):
        for key in ("script_path", "output_script_path", "highlight_script_path", "composition_script_path", "video_clip_json_path"):
            loaded = _load_movie_story_script_items_for_status(str(result.get(key) or ""))
            if loaded:
                result["script_items"] = loaded
                break

    cleaned: list[dict[str, Any]] = []
    if isinstance(result.get("script_items"), list):
        for idx, item in enumerate(result.get("script_items") or [], start=1):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            narration = str(
                row.get("narration")
                or row.get("new_content")
                or row.get("content")
                or row.get("text")
                or row.get("main_text_evidence")
                or ""
            ).strip()
            narration = sanitize_deliverable_narration_text(narration)
            if not narration:
                continue
            row["narration"] = narration
            row.setdefault("text", narration)
            row.setdefault("_id", idx)
            row.setdefault("id", idx)
            cleaned.append(row)

    if cleaned:
        result["script_items"] = cleaned
        result["script_preview_ready"] = True
        result["script_item_count"] = len(cleaned)
        result["job_contract"] = "movie_story_script_preview"
        data["script_items"] = cleaned

    data["result"] = result
    return data

def _job_status_response(task_id: str, payload: dict[str, Any]) -> JobStatusResponse:
    payload = _normalize_movie_story_script_status_payload(payload)
    status = str(payload.get("status") or "processing")
    state = int(payload.get("state") or _state_from_status(status))
    videos = payload.get("videos") or []
    combined_videos = payload.get("combined_videos") or []
    return JobStatusResponse(
        task_id=task_id,
        job_type=str(payload.get("job_type") or "video"),
        status=status,
        state=state,
        progress=int(payload.get("progress") or 0),
        message=str(payload.get("message") or ""),
        error=str(payload.get("error") or ""),
        task_dir=str(payload.get("task_dir") or ""),
        videos=list(videos if isinstance(videos, list) else []),
        combined_videos=list(combined_videos if isinstance(combined_videos, list) else []),
        is_running=bool(payload.get("is_running", False)),
        payload=payload,
    )



def _history_item_response(item: dict[str, Any]) -> JobHistoryItem:
    task_id = str(item.get("task_id") or "")
    snapshot = _runner_api()["get_task_snapshot"](task_id) if task_id else None
    live = dict(item)
    is_running = False
    if snapshot:
        live.update({k: v for k, v in snapshot.items() if v not in (None, "")})
        is_running = bool(snapshot.get("is_running", False))
    return JobHistoryItem(
        task_id=task_id,
        job_type=str(live.get("job_type") or "video"),
        status=str(live.get("status") or "processing"),
        progress=int(live.get("progress") or 0),
        message=str(live.get("message") or ""),
        error=str(live.get("error") or ""),
        task_dir=str(live.get("task_dir") or ""),
        project_id=str(live.get("project_id") or ""),
        created_at=str(live.get("created_at") or ""),
        updated_at=str(live.get("updated_at") or ""),
        is_running=is_running,
    )


@router.get("", response_model=JobListResponse)
def list_my_jobs(
    user: auth_store.StoredUser = Depends(require_user),
    project_id: str = Query(default=""),
    limit: int = Query(default=60, ge=1, le=200),
):
    if project_id:
        item = project_repository.get_project(user.email, project_id)
        if not item:
            raise HTTPException(status_code=404, detail="project_not_found")
        items = [j for j in job_history.list_project_jobs(project_id, limit=limit) if str(j.get("owner") or "").lower() == user.email.lower()]
    else:
        items = job_history.list_jobs(user.email, limit=limit)
    return JobListResponse(items=[_history_item_response(item) for item in items])


@router.get("/workers/status", response_model=JobWorkerStatusResponse)
def get_worker_status(user: auth_store.StoredUser = Depends(require_user)):
    status = _runner_api().get("get_local_job_worker_status", lambda: {
        "backend": "unknown",
        "max_workers": 0,
        "tracked_jobs": 0,
        "queued": 0,
        "running": 0,
        "done": 0,
        "cancel_requested": 0,
    })()
    return JobWorkerStatusResponse(**status)



@router.get("/{task_id}/events", response_model=JobEventListResponse)
def get_job_events(
    task_id: str,
    user: auth_store.StoredUser = Depends(require_user),
    limit: int = Query(default=200, ge=1, le=500),
):
    snapshot = _runner_api()["get_task_snapshot"](task_id)
    history = _assert_job_owner(task_id, user.email, snapshot)
    if not snapshot and not history:
        raise HTTPException(status_code=404, detail="task_not_found")
    items = [JobEventItem(**item) for item in job_events.list_events(task_id, owner=user.email, limit=limit)]
    return JobEventListResponse(items=items)


@router.get("/{task_id}", response_model=JobStatusResponse)
def get_job_status(task_id: str, user: auth_store.StoredUser = Depends(require_user)):
    snapshot = _runner_api()["get_task_snapshot"](task_id)
    history = _assert_job_owner(task_id, user.email, snapshot)
    if snapshot:
        return _job_status_response(task_id, dict(snapshot))
    if history:
        payload = dict(history)
        result = payload.pop("result", None)
        if isinstance(result, dict):
            payload.update({"result": result})
        return _job_status_response(task_id, payload)
    raise HTTPException(status_code=404, detail="task_not_found")


@router.post("/{task_id}/cancel", response_model=JobCancelResponse)
def cancel_job(task_id: str, user: auth_store.StoredUser = Depends(require_user)):
    snapshot = _runner_api()["get_task_snapshot"](task_id)
    history = _assert_job_owner(task_id, user.email, snapshot)
    if not snapshot and not history:
        raise HTTPException(status_code=404, detail="task_not_found")
    status = str((snapshot or history or {}).get("status") or "")
    if status in {"complete", "failed", "cancelled"}:
        return JobCancelResponse(task_id=task_id, status=status, message="job already finished")
    _runner_api()["request_job_cancel"](task_id)
    next_snapshot = _runner_api()["get_task_snapshot"](task_id) or job_history.get_job(task_id) or {}
    return JobCancelResponse(
        task_id=task_id,
        status=str(next_snapshot.get("status") or "cancel_requested"),
        message=str(next_snapshot.get("message") or "cancel requested"),
    )
