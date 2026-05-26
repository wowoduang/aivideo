from __future__ import annotations

import os
from typing import Any, Dict, Optional
from uuid import uuid4

from loguru import logger

from app.models import const
from app.services import job_events, job_history, state as sm
from app.services.process_control import tracked_process_counts
from app.utils import utils


JOB_FUNCTION_PATH = "app.services.rq_job_runner.execute_enqueued_job"


def _redis_url() -> str:
    return os.getenv("AIVIDEO_RQ_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"


def _queue_name() -> str:
    return os.getenv("AIVIDEO_RQ_QUEUE", "aivideo_jobs") or "aivideo_jobs"


def _job_timeout() -> int:
    raw = os.getenv("AIVIDEO_RQ_JOB_TIMEOUT_SECONDS", os.getenv("AIVIDEO_JOB_TIMEOUT_SECONDS", "7200"))
    try:
        return max(60, int(raw))
    except ValueError:
        return 7200


def _optional_rq():
    try:
        import redis  # type: ignore
        import rq  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on deployment extras
        raise RuntimeError(
            "RQ backend requested but optional dependencies are missing. "
            "Install with: pip install redis rq"
        ) from exc
    return redis, rq


def _queue():
    redis, rq = _optional_rq()
    connection = redis.from_url(_redis_url())
    return rq.Queue(_queue_name(), connection=connection), connection, rq


def _normalize_owner(owner_email: str) -> str:
    return str(owner_email or "").strip().lower()


def _record_queued(*, task_id: str, job_type: str, owner_email: str, project_id: str, payload: Dict[str, Any]) -> None:
    task_dir = utils.task_dir(task_id)
    owner = _normalize_owner(owner_email)
    sm.state.update_task(
        task_id,
        state=const.TASK_STATE_PROCESSING,
        progress=0,
        job_type=job_type,
        status="queued",
        message="queued:rqueue",
        task_dir=task_dir,
        owner_email=owner,
        project_id=str(project_id or ""),
        queue_backend="rq",
    )
    if job_history.get_job(task_id) is None:
        job_history.record_job(
            owner=owner,
            task_id=task_id,
            project_id=project_id,
            job_type=job_type,
            task_dir=task_dir,
            status="queued",
            progress=0,
            message="queued:rqueue",
        )
    else:
        job_history.update_job(task_id=task_id, status="queued", progress=0, message="queued:rqueue", error="")
    try:
        job_events.record_event(
            owner=owner,
            task_id=task_id,
            project_id=str(project_id or ""),
            job_type=job_type,
            event_type="queued",
            status="queued",
            progress=0,
            message="queued:rqueue",
            metadata={"backend": "rq", "queue": _queue_name(), "payload_keys": sorted(list(payload.keys()))[:40]},
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("failed to record rq queued event for {}: {}", task_id, exc)


def _enqueue_job(*, job_type: str, payload: Dict[str, Any], task_id: str = "", owner_email: str = "", project_id: str = "") -> str:
    task_id = str(task_id or uuid4())
    payload = dict(payload or {})
    _record_queued(task_id=task_id, job_type=job_type, owner_email=owner_email, project_id=project_id, payload=payload)
    queue, _connection, _rq = _queue()
    queue.enqueue(
        execute_enqueued_job,
        job_type=job_type,
        task_id=task_id,
        payload=payload,
        owner_email=_normalize_owner(owner_email),
        project_id=str(project_id or ""),
        job_id=task_id,
        job_timeout=_job_timeout(),
        result_ttl=int(os.getenv("AIVIDEO_RQ_RESULT_TTL_SECONDS", "86400")),
        failure_ttl=int(os.getenv("AIVIDEO_RQ_FAILURE_TTL_SECONDS", "604800")),
    )
    return task_id


def start_rq_video_job(params: Any, task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    payload = params.model_dump() if hasattr(params, "model_dump") else dict(params or {})
    return _enqueue_job(job_type="video", payload=payload, task_id=task_id, owner_email=owner_email, project_id=project_id)


def start_rq_highlight_script_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    return _enqueue_job(job_type="highlight_script", payload=dict(request or {}), task_id=task_id, owner_email=owner_email, project_id=project_id)


def start_rq_movie_story_script_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    return _enqueue_job(job_type="movie_story_script", payload=dict(request or {}), task_id=task_id, owner_email=owner_email, project_id=project_id)


def start_rq_subtitle_job(request: Dict[str, Any], task_id: str = "", *, owner_email: str = "", project_id: str = "") -> str:
    return _enqueue_job(job_type="subtitle", payload=dict(request or {}), task_id=task_id, owner_email=owner_email, project_id=project_id)


def execute_enqueued_job(*, job_type: str, task_id: str, payload: Dict[str, Any], owner_email: str = "", project_id: str = "") -> str:
    """RQ worker entry point.

    Run workers with:
      AIVIDEO_JOB_BACKEND=rq rq worker aivideo_jobs --with-scheduler

    The API process persists queued/cancel_requested state. The worker updates
    job_history/job_events as it runs, so the API can report progress even when
    process-local memory is not shared.
    """

    from app.services.local_job_runner import run_job_inline

    return run_job_inline(
        task_id=task_id,
        job_type=job_type,
        payload=dict(payload or {}),
        owner_email=owner_email,
        project_id=project_id,
    )


def get_rq_task_snapshot(task_id: str) -> Optional[Dict[str, Any]]:
    task_id = str(task_id or "").strip()
    if not task_id:
        return None
    live = sm.state.get_task(task_id)
    history = job_history.get_job(task_id)
    if not live and not history:
        return None
    payload: Dict[str, Any] = dict(history or {})
    if live:
        payload.update(dict(live))
    payload["task_id"] = task_id
    payload.setdefault("job_type", "video")
    payload.setdefault("task_dir", utils.task_dir(task_id))
    payload.setdefault("status", "processing")
    payload.setdefault("progress", 0)
    payload["is_running"] = str(payload.get("status") or "") in {"queued", "running", "processing", "cancel_requested"}
    payload["queue_backend"] = "rq"
    return payload


def request_rq_job_cancel(task_id: str) -> bool:
    task_id = str(task_id or "").strip()
    if not task_id:
        return False
    # Persist cancellation so external workers can observe it via job_history.
    history = job_history.get_job(task_id)
    progress = int((history or {}).get("progress") or 0)
    if history:
        job_history.update_job(task_id=task_id, status="cancel_requested", progress=progress, message="cancel requested", error="")
        try:
            job_events.record_event(
                owner=str(history.get("owner") or ""),
                task_id=task_id,
                project_id=str(history.get("project_id") or ""),
                job_type=str(history.get("job_type") or ""),
                event_type="cancel_requested",
                status="cancel_requested",
                progress=progress,
                message="cancel requested",
                metadata={"backend": "rq"},
            )
        except Exception as _e:
            logger.warning("rq 状态上报失败: {}", _e)
    try:
        queue, connection, rq = _queue()
        job = rq.job.Job.fetch(task_id, connection=connection)
        # This cancels/dequeues jobs that have not started yet. Running workers
        # exit cooperatively through local_job_runner.is_cancel_requested().
        try:
            job.cancel()
        except Exception as _e:
            logger.warning("rq job.cancel 失败: {}", _e)
        try:
            if job.get_status(refresh=True) in {"queued", "deferred", "scheduled"}:
                job.delete()
        except Exception as _e:
            logger.warning("rq job.delete 失败: {}", _e)
    except Exception as exc:
        logger.debug("rq cancel best-effort failed for {}: {}", task_id, exc)
    return True


def get_rq_job_worker_status() -> Dict[str, Any]:
    status = {
        "backend": "rq",
        "max_workers": 0,
        "tracked_jobs": 0,
        "queued": 0,
        "running": 0,
        "done": 0,
        "cancel_requested": 0,
        "active_processes": 0,
        "process_tasks": {},
        "queue": _queue_name(),
        "redis_url": _redis_url(),
        "available": False,
    }
    try:
        queue, connection, rq = _queue()
        workers = rq.Worker.all(connection=connection)
        started = rq.registry.StartedJobRegistry(queue=queue)
        finished = rq.registry.FinishedJobRegistry(queue=queue)
        failed = rq.registry.FailedJobRegistry(queue=queue)
        deferred = rq.registry.DeferredJobRegistry(queue=queue)
        scheduled = rq.registry.ScheduledJobRegistry(queue=queue)
        proc_counts = tracked_process_counts()
        status.update({
            "available": True,
            "max_workers": len(workers),
            "tracked_jobs": int(queue.count or 0) + len(started) + len(deferred) + len(scheduled),
            "queued": int(queue.count or 0) + len(deferred) + len(scheduled),
            "running": len(started),
            "done": len(finished) + len(failed),
            "cancel_requested": 0,
            "active_processes": int(proc_counts.get("active_processes", 0) or 0),
            "process_tasks": proc_counts.get("tasks", {}),
        })
    except Exception as exc:
        status["error"] = str(exc)
    return status
