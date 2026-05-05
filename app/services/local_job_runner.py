from __future__ import annotations

import os
import threading
import traceback
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from loguru import logger

from app.models import const
from app.models.schema import VideoClipParams
from app.services import state as sm
from app.utils import utils


_JOB_THREADS: Dict[str, threading.Thread] = {}
_JOB_THREADS_LOCK = threading.Lock()


def _persist_job_metadata(task_id: str, *, status: str, progress: int, message: str = "", error: str = "", result: Optional[Dict[str, Any]] = None) -> None:
    existing = sm.state.get_task(task_id) or {}
    owner_email = str(existing.get("owner_email") or "").strip().lower()
    project_id = str(existing.get("project_id") or "").strip()
    job_type = str(existing.get("job_type") or "").strip()
    if not owner_email:
        return

    from app.services import job_history
    from app.repositories import artifact_repository, project_repository

    # 后端任务只更新“资源结果”，不抢改 currentStep。
    # currentStep 是用户当前停留页面，刷新时按它恢复。
    if status == "complete" and project_id and isinstance(result, dict):
        if job_type == "subtitle":
            subtitle_path = str(result.get("subtitle_path") or "").strip()
            patch: Dict[str, Any] = {"status": "draft"}
            if subtitle_path:
                patch["uploadedSubtitlePath"] = subtitle_path
            project_repository.update_project(owner_email, project_id, patch)
        else:
            artifact_repository.index_movie_story_result(owner_email, project_id, task_id, result)
            patch: Dict[str, Any] = {"status": "completed"}
            script_items = result.get("script_items")
            if isinstance(script_items, list) and script_items:
                patch["scriptItems"] = script_items
            project_repository.update_project(owner_email, project_id, patch)
    elif status == "failed" and project_id:
        # 字幕识别失败不是项目失败；保留在草稿态，允许用户回字幕页换模型重试。
        if job_type == "subtitle":
            project_repository.update_project(owner_email, project_id, {"status": "draft"})
        else:
            project_repository.update_project(owner_email, project_id, {"status": "failed"})

    if job_history.get_job(task_id) is None:
        job_history.record_job(
            owner=owner_email,
            task_id=task_id,
            project_id=project_id,
            job_type=str(existing.get("job_type") or "video"),
            task_dir=str(existing.get("task_dir") or utils.task_dir(task_id)),
            status=status,
            progress=int(progress or 0),
            message=message or str(existing.get("message") or ""),
            error=error or str(existing.get("error") or ""),
        )
    else:
        job_history.update_job(
            task_id=task_id,
            status=status,
            progress=int(progress or 0),
            message=message,
            error=error,
            result=result,
        )


def _task_status_name(state_value: int) -> str:
    if state_value == const.TASK_STATE_COMPLETE:
        return "complete"
    if state_value == const.TASK_STATE_FAILED:
        return "failed"
    return "processing"


def _cleanup_dead_threads() -> None:
    with _JOB_THREADS_LOCK:
        dead_ids = [task_id for task_id, thread in _JOB_THREADS.items() if not thread.is_alive()]
        for task_id in dead_ids:
            _JOB_THREADS.pop(task_id, None)


def _track_thread(task_id: str, thread: threading.Thread) -> None:
    _cleanup_dead_threads()
    with _JOB_THREADS_LOCK:
        _JOB_THREADS[task_id] = thread


def _update_processing_state(task_id: str, job_type: str, progress: int, message: str = "", **extra: Any) -> None:
    existing = sm.state.get_task(task_id) or {}
    payload = dict(existing)
    payload.update(extra)
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=int(progress),
        job_type=job_type,
        status="processing",
        message=message or str(payload.get("message", "") or ""),
        task_dir=str(payload.get("task_dir", utils.task_dir(task_id))),
        **{k: v for k, v in payload.items() if k not in {"state", "progress", "status", "message", "job_type", "task_dir"}},
    )


def _mark_job_failed(task_id: str, job_type: str, err: Exception, **extra: Any) -> None:
    tb = traceback.format_exc()
    logger.error(
        f"local {job_type} job failed: {task_id}\n"
        f"  error_type: {type(err).__name__}\n"
        f"  error_message: {err}\n"
        f"  traceback:\n{tb}"
    )
    existing = sm.state.get_task(task_id) or {}
    payload = dict(existing)
    payload.update(extra)
    task_dir = str(payload.get("task_dir", utils.task_dir(task_id)))
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_FAILED,
        progress=int(existing.get("progress", 0) or 0),
        job_type=job_type,
        status="failed",
        message=f"{type(err).__name__}: {err}",
        error=f"{type(err).__name__}: {err}",
        traceback=tb,
        task_dir=task_dir,
        **{k: v for k, v in payload.items() if k not in {"state", "progress", "status", "message", "error", "traceback", "job_type", "task_dir"}},
    )
    _persist_job_metadata(
        task_id,
        status="failed",
        progress=int(existing.get("progress", 0) or 0),
        message=f"{type(err).__name__}: {err}",
        error=f"{type(err).__name__}: {err}",
    )


def _mark_job_complete(task_id: str, job_type: str, *, message: str = "complete", **extra: Any) -> None:
    existing = sm.state.get_task(task_id) or {}
    task_dir = str((extra.get("task_dir") or existing.get("task_dir") or utils.task_dir(task_id)))
    # 构建 payload，保留现有 metadata，排除已单独处理的字段
    payload = dict(existing)
    payload.update(extra)
    payload = {
        k: v
        for k, v in payload.items()
        if k not in {"state", "progress", "status", "message", "job_type", "task_dir"}
    }
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_COMPLETE,
        progress=100,
        job_type=job_type,
        status="complete",
        message=message,
        task_dir=task_dir,
        **payload,
    )
    result_payload = extra.get("result") if isinstance(extra.get("result"), dict) else None
    _persist_job_metadata(task_id, status="complete", progress=100, message=message, result=result_payload)


def _run_threaded_job(
    task_id: str,
    *,
    job_type: str,
    runner: Callable[[], Dict[str, Any]],
) -> None:
    try:
        result = runner() or {}
        _mark_job_complete(task_id, job_type, result=result, **result)
    except Exception as err:
        _mark_job_failed(task_id, job_type, err)
    finally:
        _cleanup_dead_threads()


def _start_job_thread(
    *,
    task_id: str,
    job_type: str,
    runner: Callable[[], Dict[str, Any]],
    owner_email: str = "",
    project_id: str = "",
) -> str:
    task_dir = utils.task_dir(task_id)
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=0,
        job_type=job_type,
        status="processing",
        message="queued",
        task_dir=task_dir,
        owner_email=(str(owner_email or "").strip().lower()),
        project_id=str(project_id or "").strip(),
    )

    thread = threading.Thread(
        target=_run_threaded_job,
        kwargs={
            "task_id": task_id,
            "job_type": job_type,
            "runner": runner,
        },
        daemon=True,
        name=f"narrato-{job_type}-{task_id}",
    )
    thread.start()
    _track_thread(task_id, thread)
    logger.info(f"local {job_type} job started: {task_id}")
    return task_id


def _run_video_job(task_id: str, params: VideoClipParams) -> Dict[str, Any]:
    from app.services import task

    task.start_subclip_unified(task_id=task_id, params=params)
    return sm.state.get_task(task_id) or {}


def start_local_video_job(params: VideoClipParams, task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())
    return _start_job_thread(
        task_id=task_id,
        job_type="video",
        runner=lambda: _run_video_job(task_id, params),
        owner_email=owner_email,
        project_id=project_id,
    )


def start_local_highlight_script_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())

    def runner() -> Dict[str, Any]:
        def progress_callback(progress: int, message: str = "") -> None:
            _update_processing_state(task_id, "highlight_script", int(progress), message)

        from app.services.movie_story.unified_entry import run_unified_edit_request

        result = run_unified_edit_request(
            entry="highlight_script",
            request=request,
            progress_callback=progress_callback,
        )
        if not result.get("success"):
            raise RuntimeError(str(result.get("error", "highlight_script_failed")))
        return result

    return _start_job_thread(
        task_id=task_id,
        job_type="highlight_script",
        runner=runner,
        owner_email=owner_email,
        project_id=project_id,
    )


def _movie_story_scene_overrides_from_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Deprecated compatibility wrapper.

    Stage-N moved movie-story request normalization into
    app.services.movie_story.unified_entry so both old front-end entries share
    one normalized boundary.
    """

    from app.services.movie_story.unified_entry import movie_story_scene_overrides_from_request

    return movie_story_scene_overrides_from_request(request)


def start_local_movie_story_script_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())

    def runner() -> Dict[str, Any]:
        def progress_callback(progress: int, message: str = "") -> None:
            _update_processing_state(task_id, "movie_story_script", int(progress), message)

        from app.services.movie_story.unified_entry import (
            build_task_output_script_path,
            run_unified_edit_request,
        )

        # Use a task-scoped output path. A stopped run followed by “重新开始”
        # must not share the previous default video-hash script path or audit dir.
        # This prevents two still-running threads from mixing 03/05/07 artifacts.
        task_output_script_path = build_task_output_script_path(
            request=request,
            task_dir=str(utils.task_dir(task_id)),
        )

        result = run_unified_edit_request(
            entry="movie_story_script",
            request=request,
            progress_callback=progress_callback,
            output_script_path=task_output_script_path,
        )
        if not result.get("success"):
            raise RuntimeError(str(result.get("error", "movie_story_script_failed")))
        return result

    return _start_job_thread(
        task_id=task_id,
        job_type="movie_story_script",
        runner=runner,
        owner_email=owner_email,
        project_id=project_id,
    )


def start_local_subtitle_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())

    def runner() -> Dict[str, Any]:
        video_path = str(request.get("video_path", "") or "").strip()
        backend = str(request.get("backend", "") or "").strip()
        model = str(request.get("model", "") or "").strip()
        if not video_path:
            raise ValueError("video_path is required")

        _update_processing_state(task_id, "subtitle", 5, "准备提取音频")

        from app.services import subtitle as subtitle_service

        subtitle_file = subtitle_service.extract_audio_and_create_subtitle(
            video_file=video_path,
            backend_override=backend,
            model_override=model,
        )

        if not subtitle_file:
            raise RuntimeError("字幕识别失败：未生成字幕文件")

        _update_processing_state(task_id, "subtitle", 95, "整理识别结果")

        return {
            "success": True,
            "subtitle_path": subtitle_file,
            "backend": backend or "",
            "model": model or "",
        }

    return _start_job_thread(
        task_id=task_id,
        job_type="subtitle",
        runner=runner,
        owner_email=owner_email,
        project_id=project_id,
    )


def get_task_snapshot(task_id: str) -> Optional[Dict]:
    task_data = sm.state.get_task(task_id)
    if not task_data:
        return None

    snapshot = dict(task_data)
    snapshot["task_id"] = task_id
    snapshot.setdefault("job_type", "video")
    snapshot.setdefault("task_dir", utils.task_dir(task_id))
    snapshot["status"] = _task_status_name(int(snapshot.get("state", const.TASK_STATE_PROCESSING) or 0))

    with _JOB_THREADS_LOCK:
        thread = _JOB_THREADS.get(task_id)
    snapshot["is_running"] = bool(thread and thread.is_alive())
    return snapshot
