from __future__ import annotations

import os
import queue
import threading
import traceback
from concurrent.futures import Future
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from loguru import logger

from app.models import const
from app.models.schema import VideoClipParams
from app.services import state as sm
from app.services import runtime_context
from app.services.process_control import ProcessCancelled, cancel_task_processes, tracked_process_counts
from app.utils import utils


_JOB_FUTURES: Dict[str, Future] = {}
_JOB_FUTURES_LOCK = threading.Lock()
_JOB_EXECUTOR: Optional[_DaemonJobExecutor] = None
_JOB_EXECUTOR_LOCK = threading.Lock()
_CANCEL_REQUESTS: set[str] = set()
_CANCEL_LOCK = threading.Lock()


class JobCancelled(RuntimeError):
    pass


class _DaemonJobExecutor:
    """Small daemon worker pool used by the local single-process runner.

    ThreadPoolExecutor keeps non-daemon worker threads and can block CLI/test
    process shutdown after background jobs. This pool preserves the Future API
    needed by the router while making local workers daemonized and bounded.
    Production deployments can still replace this runner with Celery/RQ later.
    """

    def __init__(self, max_workers: int, thread_name_prefix: str = "aivideo-job") -> None:
        self.max_workers = max(1, int(max_workers or 1))
        self._queue: queue.Queue = queue.Queue()
        self._shutdown = False
        self._threads: list[threading.Thread] = []
        for idx in range(self.max_workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"{thread_name_prefix}_{idx}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, fn: Callable[..., Dict[str, Any]], *args: Any, **kwargs: Any) -> Future:
        future: Future = Future()
        if self._shutdown:
            future.set_exception(RuntimeError("local_job_executor_shutdown"))
            return future
        self._queue.put((future, fn, args, kwargs))
        return future

    def shutdown(self, wait: bool = False, cancel_futures: bool = False) -> None:
        self._shutdown = True
        if cancel_futures:
            try:
                while True:
                    future, _fn, _args, _kwargs = self._queue.get_nowait()
                    future.cancel()
                    self._queue.task_done()
            except queue.Empty:
                pass  # IO/队列清理，忽略异常
        for _ in self._threads:
            self._queue.put(None)
        if wait:
            for thread in self._threads:
                thread.join(timeout=2)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                future, fn, args, kwargs = item
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    result = fn(*args, **kwargs)
                except BaseException as exc:  # propagate cancellation/failure to Future
                    future.set_exception(exc)
                else:
                    future.set_result(result)
            finally:
                self._queue.task_done()


def _max_local_workers() -> int:
    raw = str(os.getenv("AIVIDEO_LOCAL_JOB_MAX_WORKERS", "2") or "2").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _job_executor() -> _DaemonJobExecutor:
    global _JOB_EXECUTOR
    with _JOB_EXECUTOR_LOCK:
        if _JOB_EXECUTOR is None:
            _JOB_EXECUTOR = _DaemonJobExecutor(
                max_workers=_max_local_workers(),
                thread_name_prefix="aivideo-job",
            )
        return _JOB_EXECUTOR


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

    try:
        from app.services import job_events

        event_type = "status_update"
        if status in {"queued", "running", "complete", "failed", "cancelled", "cancel_requested"}:
            event_type = status
        job_events.record_event(
            owner=owner_email,
            task_id=task_id,
            project_id=project_id,
            job_type=str(existing.get("job_type") or "video"),
            event_type=event_type,
            status=status,
            progress=int(progress or 0),
            message=message or str(existing.get("message") or ""),
            metadata={"error": error} if error else {},
        )
    except Exception as exc:  # pragma: no cover - observability must not break jobs
        logger.debug("failed to record job event for {}: {}", task_id, exc)


def _task_status_name(state_value: int) -> str:
    if state_value == const.TASK_STATE_COMPLETE:
        return "complete"
    if state_value == const.TASK_STATE_FAILED:
        return "failed"
    return "processing"


def request_job_cancel(task_id: str) -> bool:
    task_id = str(task_id or "").strip()
    if not task_id:
        return False
    with _CANCEL_LOCK:
        _CANCEL_REQUESTS.add(task_id)
    terminated_processes = cancel_task_processes(task_id)
    cancelled_before_start = False
    with _JOB_FUTURES_LOCK:
        future = _JOB_FUTURES.get(task_id)
        if future is not None:
            cancelled_before_start = future.cancel()
    existing = sm.state.get_task(task_id) or {}
    payload = dict(existing)
    status = "cancelled" if cancelled_before_start else "cancel_requested"
    progress = int(existing.get("progress", 0) or 0)
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_FAILED if cancelled_before_start else const.TASK_STATE_PROCESSING,
        progress=progress,
        status=status,
        job_type=str(existing.get("job_type") or "video"),
        message="cancelled" if cancelled_before_start else (f"cancel requested; terminated_processes={terminated_processes}" if terminated_processes else "cancel requested"),
        task_dir=str(existing.get("task_dir", utils.task_dir(task_id))),
        **{k: v for k, v in payload.items() if k not in {"state", "progress", "status", "message", "job_type", "task_dir"}},
    )
    _persist_job_metadata(
        task_id,
        status=status,
        progress=progress,
        message="cancelled" if cancelled_before_start else (f"cancel requested; terminated_processes={terminated_processes}" if terminated_processes else "cancel requested"),
    )
    return True


def is_cancel_requested(task_id: str) -> bool:
    task_id = str(task_id or "").strip()
    if not task_id:
        return False
    with _CANCEL_LOCK:
        if task_id in _CANCEL_REQUESTS:
            return True
    snapshot = sm.state.get_task(task_id) or {}
    if str(snapshot.get("status") or "") == "cancel_requested":
        return True
    # Cross-process workers (RQ/Celery/etc.) cannot see this process' memory state.
    # Persisted job history is therefore the cancellation source of truth for
    # production queue backends.
    try:
        from app.services import job_history

        history = job_history.get_job(task_id) or {}
        return str(history.get("status") or "") == "cancel_requested"
    except Exception:
        return False


def _raise_if_cancelled(task_id: str) -> None:
    if is_cancel_requested(task_id):
        raise JobCancelled("job_cancelled")


def _cleanup_dead_threads() -> None:
    should_shutdown_idle_executor = False
    with _JOB_FUTURES_LOCK:
        dead_ids = [task_id for task_id, future in _JOB_FUTURES.items() if future.done()]
        for task_id in dead_ids:
            _JOB_FUTURES.pop(task_id, None)
        should_shutdown_idle_executor = not _JOB_FUTURES
    if should_shutdown_idle_executor:
        _shutdown_idle_executor()


def _shutdown_idle_executor() -> None:
    global _JOB_EXECUTOR
    with _JOB_EXECUTOR_LOCK:
        executor = _JOB_EXECUTOR
        if executor is None:
            return
        _JOB_EXECUTOR = None
    executor.shutdown(wait=False, cancel_futures=False)


def _track_future(task_id: str, future: Future) -> None:
    _cleanup_dead_threads()
    future.add_done_callback(lambda _future: _cleanup_dead_threads())
    with _JOB_FUTURES_LOCK:
        _JOB_FUTURES[task_id] = future


def _update_processing_state(task_id: str, job_type: str, progress: int, message: str = "", **extra: Any) -> None:
    _raise_if_cancelled(task_id)
    existing = sm.state.get_task(task_id) or {}
    payload = dict(existing)
    payload.update(extra)
    status = str(payload.pop("status", "processing") or "processing")
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=int(progress),
        job_type=job_type,
        status=status,
        message=message or str(payload.get("message", "") or ""),
        task_dir=str(payload.get("task_dir", utils.task_dir(task_id))),
        **{k: v for k, v in payload.items() if k not in {"state", "progress", "status", "message", "job_type", "task_dir"}},
    )
    _persist_job_metadata(task_id, status=status, progress=int(progress), message=message or str(payload.get("message", "") or ""))


def _mark_job_cancelled(task_id: str, job_type: str, *, message: str = "cancelled") -> None:
    existing = sm.state.get_task(task_id) or {}
    payload = dict(existing)
    progress = int(existing.get("progress", 0) or 0)
    task_dir = str(payload.get("task_dir", utils.task_dir(task_id)))
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_FAILED,
        progress=progress,
        job_type=job_type,
        status="cancelled",
        message=message,
        error="",
        task_dir=task_dir,
        **{k: v for k, v in payload.items() if k not in {"state", "progress", "status", "message", "error", "job_type", "task_dir"}},
    )
    _persist_job_metadata(task_id, status="cancelled", progress=progress, message=message, error="")
    with _CANCEL_LOCK:
        _CANCEL_REQUESTS.discard(task_id)


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
    existing = sm.state.get_task(task_id) or {}
    owner_email = str(existing.get("owner_email") or "").strip().lower()
    project_id = str(existing.get("project_id") or "").strip()
    with runtime_context.job_context(owner=owner_email, task_id=task_id, project_id=project_id):
        try:
            _raise_if_cancelled(task_id)
            _update_processing_state(
                task_id,
                job_type,
                max(1, int(existing.get("progress", 0) or 0)),
                "running",
                status="running",
            )
            result = runner() or {}
            _raise_if_cancelled(task_id)
            result_extra = dict(result) if isinstance(result, dict) else {}
            result_extra.pop("result", None)
            _mark_job_complete(task_id, job_type, result=result, **result_extra)
        except (JobCancelled, ProcessCancelled):
            _mark_job_cancelled(task_id, job_type)
        except Exception as err:
            _mark_job_failed(task_id, job_type, err)
        finally:
            with _CANCEL_LOCK:
                if str(task_id) in _CANCEL_REQUESTS and (sm.state.get_task(task_id) or {}).get("status") == "cancelled":
                    _CANCEL_REQUESTS.discard(str(task_id))
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
    with _CANCEL_LOCK:
        _CANCEL_REQUESTS.discard(task_id)
    normalized_owner = str(owner_email or "").strip().lower()
    normalized_project = str(project_id or "").strip()
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=0,
        job_type=job_type,
        status="queued",
        message="queued",
        task_dir=task_dir,
        owner_email=normalized_owner,
        project_id=normalized_project,
    )
    _persist_job_metadata(task_id, status="queued", progress=0, message="queued")

    future = _job_executor().submit(
        _run_threaded_job,
        task_id,
        job_type=job_type,
        runner=runner,
    )
    _track_future(task_id, future)
    logger.info(f"local {job_type} job queued: {task_id} (max_workers={_max_local_workers()})")
    return task_id


def _run_video_job(task_id: str, params: VideoClipParams) -> Dict[str, Any]:
    from app.services import task

    task.start_subclip_unified(task_id=task_id, params=params)
    return sm.state.get_task(task_id) or {}


def _load_movie_story_script_items_from_path(path: str) -> list[Dict[str, Any]]:
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
        except Exception as exc:
            logger.warning("failed to read movie_story script artifact: path={}, error={}", str(file_path), exc)
            continue
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            items = data.get("script_items") or data.get("items") or data.get("segments") or data.get("script")
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
    return []


def _normalize_movie_story_script_preview_result(task_id: str, request: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise RuntimeError("movie_story_script_result_not_dict")

    normalized = dict(result)

    items = normalized.get("script_items")
    if not isinstance(items, list) or not items:
        for key in ("script_path", "output_script_path", "highlight_script_path", "composition_script_path", "video_clip_json_path"):
            loaded = _load_movie_story_script_items_from_path(str(normalized.get(key) or ""))
            if loaded:
                items = loaded
                normalized["script_items"] = loaded
                break

    cleaned: list[Dict[str, Any]] = []
    if isinstance(normalized.get("script_items"), list):
        for idx, item in enumerate(normalized.get("script_items") or [], start=1):
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
            if not narration:
                continue
            row["narration"] = narration
            row.setdefault("text", narration)
            row.setdefault("_id", idx)
            row.setdefault("id", idx)
            row.setdefault("section_title", row.get("title") or row.get("segment_title") or "")
            cleaned.append(row)

    if not cleaned:
        keys = ",".join(sorted(str(k) for k in normalized.keys()))
        raise RuntimeError(f"movie_story_script_missing_script_items: result_keys={keys}")

    normalized["script_items"] = cleaned
    normalized["success"] = bool(normalized.get("success", True))
    normalized["script_preview_ready"] = True
    normalized["script_item_count"] = len(cleaned)
    normalized["job_contract"] = "movie_story_script_preview"
    normalized["auto_compose_disabled"] = True
    normalized.setdefault("video_path", str(request.get("video_path") or ""))
    normalized.setdefault("subtitle_path", str(request.get("subtitle_path") or ""))
    return normalized

def _compose_direct_cut_movie_story_result(
    task_id: str,
    request: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    if not bool(result.get("direct_cut_first")):
        return result

    video_path = str(request.get("video_path") or result.get("video_path") or "").strip()
    script_path = str(
        result.get("highlight_script_path")
        or result.get("composition_script_path")
        or result.get("script_path")
        or ""
    ).strip()
    if not video_path or not script_path:
        logger.warning(
            "direct-cut movie_story result cannot auto-compose: video_path={}, script_path={}",
            bool(video_path),
            bool(script_path),
        )
        return result

    logger.warning(
        "direct-cut movie_story script complete; auto composing final video: task_id={}, script_path={}",
        task_id,
        script_path,
    )
    _update_processing_state(task_id, "movie_story_script", 90, "字幕时间直切：正在合成成片")
    params = VideoClipParams(
        video_clip_json_path=script_path,
        video_clip_json=result.get("script_items") if isinstance(result.get("script_items"), list) else [],
        video_origin_path=video_path,
        subtitle_enabled=False,
        bgm_type="none",
        bgm_name="none",
        bgm_volume=0.0,
        original_volume=1.0,
    )
    video_result = _run_video_job(task_id, params)
    merged = dict(result)
    for key in ("videos", "combined_videos"):
        values = video_result.get(key)
        if values:
            merged[key] = values
    merged["direct_cut_video_composed"] = bool(merged.get("videos"))
    merged["video_compose_result"] = {
        "videos": merged.get("videos") or [],
        "combined_videos": merged.get("combined_videos") or [],
    }
    return merged


def build_job_runner(job_type: str, task_id: str, payload: Dict[str, Any] | VideoClipParams) -> Callable[[], Dict[str, Any]]:
    """Build the callable used by both local and external queue workers.

    This keeps the business execution path identical for local daemon workers
    and production queue backends such as RQ. The payload is intentionally
    JSON-serializable for external queues.
    """

    job_type = str(job_type or "video").strip()

    if job_type == "video":
        params = payload if isinstance(payload, VideoClipParams) else VideoClipParams(**dict(payload or {}))
        return lambda: _run_video_job(task_id, params)

    request = dict(payload or {})

    if job_type == "highlight_script":
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
        return runner

    if job_type == "movie_story_script":
        def runner() -> Dict[str, Any]:
            def progress_callback(progress: int, message: str = "") -> None:
                _update_processing_state(task_id, "movie_story_script", int(progress), message)

            from app.services.movie_story.unified_entry import (
                build_task_output_script_path,
                run_unified_edit_request,
            )

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
            result = _normalize_movie_story_script_preview_result(task_id, request, result)

            # FORMAL FACT-EVIDENCE POST-PROCESSOR:
            # After movie_story_script writes the selected highlight files, build
            # selected-highlight visual evidence for review, optional VLM checks,
            # and the two-round narration input package.
            #
            # Producer:
            # - local movie_story_script job.
            #
            # Inputs:
            # - request["video_path"]
            # - result["script_path"] or task_output_script_path
            #
            # Outputs:
            # - *_selected_highlight_keyframes.json
            # - *_selected_highlight_visual_evidence.json
            # - *_two_round_input_packages.json
            # - *_selected_highlight_contact_sheet.jpg
            #
            # NOT FOR:
            # - selecting highlights
            # - generating narration
            # - hiding failed frame extraction
            movie_story_mode = str(
                request.get("movie_story_mode") or request.get("movie_story_feature_mode") or "two_round"
            ).strip().lower()
            visual_evidence_enabled = movie_story_mode == "two_round_visual" or bool(
                request.get("movie_story_enable_visual_evidence", False)
            )
            if visual_evidence_enabled:
                _update_processing_state(task_id, "movie_story_script", 96, "生成高光视觉事实证据")
                from app.services.movie_story.selected_highlight_visual_evidence_workflow import (
                    build_selected_highlight_visual_evidence_package,
                )

                visual_evidence_result = build_selected_highlight_visual_evidence_package(
                    video_path=str(request.get("video_path") or result.get("video_path") or ""),
                    output_script_path=str(result.get("script_path") or task_output_script_path),
                    max_frames_per_highlight=int(request.get("movie_story_selected_highlight_max_frames") or 6),
                    write_contact_sheet=True,
                )
                result.update(visual_evidence_result)
            return result
        return runner

    if job_type == "subtitle":
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

            try:
                from app.services import usage_meter
                from app.services.media_duration import probe_media_duration

                usage_meter.record_asr_usage(
                    owner=runtime_context.current_owner() or (sm.state.get_task(task_id) or {}).get("owner_email", ""),
                    provider=backend or "auto",
                    model=model,
                    audio_seconds=probe_media_duration(video_path),
                    task_id=task_id,
                    project_id=runtime_context.current_project_id() or (sm.state.get_task(task_id) or {}).get("project_id", ""),
                    metadata={"video_path": video_path, "subtitle_path": subtitle_file},
                )
            except Exception as _e:
                logger.warning("用量上报失败（非致命）: {}", _e)

            return {
                "success": True,
                "subtitle_path": subtitle_file,
                "backend": backend or "",
                "model": model or "",
            }
        return runner

    raise ValueError(f"unsupported_job_type:{job_type}")


def run_job_inline(
    *,
    task_id: str,
    job_type: str,
    payload: Dict[str, Any],
    owner_email: str = "",
    project_id: str = "",
) -> str:
    """Run a job synchronously inside an external worker process.

    RQ/Celery workers call this function after dequeuing. It recreates the
    memory snapshot needed by progress callbacks, while job_history/job_events
    remain the cross-process source of truth for the API server.
    """

    task_id = str(task_id or uuid4())
    task_dir = utils.task_dir(task_id)
    normalized_owner = str(owner_email or "").strip().lower()
    normalized_project = str(project_id or "").strip()
    with _CANCEL_LOCK:
        _CANCEL_REQUESTS.discard(task_id)
    existing = sm.state.get_task(task_id) or {}
    if not existing:
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_PROCESSING,
            progress=0,
            job_type=job_type,
            status="queued",
            message="queued",
            task_dir=task_dir,
            owner_email=normalized_owner,
            project_id=normalized_project,
        )
    _persist_job_metadata(task_id, status="queued", progress=0, message="queued")
    runner = build_job_runner(job_type, task_id, payload)
    _run_threaded_job(task_id, job_type=job_type, runner=runner)
    return task_id


def start_local_video_job(params: VideoClipParams, task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())
    return _start_job_thread(
        task_id=task_id,
        job_type="video",
        runner=build_job_runner("video", task_id, params),
        owner_email=owner_email,
        project_id=project_id,
    )


def start_local_highlight_script_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())
    return _start_job_thread(
        task_id=task_id,
        job_type="highlight_script",
        runner=build_job_runner("highlight_script", task_id, request),
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
    return _start_job_thread(
        task_id=task_id,
        job_type="movie_story_script",
        runner=build_job_runner("movie_story_script", task_id, request),
        owner_email=owner_email,
        project_id=project_id,
    )


def start_local_subtitle_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())
    return _start_job_thread(
        task_id=task_id,
        job_type="subtitle",
        runner=build_job_runner("subtitle", task_id, request),
        owner_email=owner_email,
        project_id=project_id,
    )


def get_local_job_worker_status() -> Dict[str, Any]:
    _cleanup_dead_threads()
    with _JOB_FUTURES_LOCK:
        items = list(_JOB_FUTURES.items())
    queued = 0
    running = 0
    done = 0
    for _task_id, future in items:
        if future.running():
            running += 1
        elif future.done():
            done += 1
        else:
            queued += 1
    process_counts = tracked_process_counts()
    return {
        "backend": "threadpool",
        "max_workers": _max_local_workers(),
        "tracked_jobs": len(items),
        "queued": queued,
        "running": running,
        "done": done,
        "cancel_requested": len(_CANCEL_REQUESTS),
        "active_processes": int(process_counts.get("active_processes", 0) or 0),
        "process_tasks": process_counts.get("tasks", {}),
    }

def get_task_snapshot(task_id: str) -> Optional[Dict]:
    task_data = sm.state.get_task(task_id)
    if not task_data:
        return None

    snapshot = dict(task_data)
    snapshot["task_id"] = task_id
    snapshot.setdefault("job_type", "video")
    snapshot.setdefault("task_dir", utils.task_dir(task_id))
    existing_status = str(snapshot.get("status") or "").strip()
    snapshot["status"] = existing_status or _task_status_name(int(snapshot.get("state", const.TASK_STATE_PROCESSING) or 0))

    with _JOB_FUTURES_LOCK:
        future = _JOB_FUTURES.get(task_id)
    snapshot["is_running"] = bool(future and not future.done())
    return snapshot
