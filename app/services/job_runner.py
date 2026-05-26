from __future__ import annotations

import os
from typing import Any, Callable, Dict


def configured_backend() -> str:
    return str(os.getenv("AIVIDEO_JOB_BACKEND", "local") or "local").strip().lower()


def is_rq_backend() -> bool:
    return configured_backend() in {"rq", "redis", "redis-rq"}


def runner_api() -> Dict[str, Callable[..., Any]]:
    """Return the active job runner API.

    Default remains the in-process local runner for developer installs. Set
    AIVIDEO_JOB_BACKEND=rq to enqueue jobs to Redis/RQ and run them in separate
    worker processes.
    """

    if is_rq_backend():
        from app.services.rq_job_runner import (
            get_rq_job_worker_status,
            get_rq_task_snapshot,
            request_rq_job_cancel,
            start_rq_highlight_script_job,
            start_rq_movie_story_script_job,
            start_rq_subtitle_job,
            start_rq_video_job,
        )

        return {
            "backend": "rq",
            "get_task_snapshot": get_rq_task_snapshot,
            "get_local_job_worker_status": get_rq_job_worker_status,
            "start_local_highlight_script_job": start_rq_highlight_script_job,
            "start_local_movie_story_script_job": start_rq_movie_story_script_job,
            "start_local_subtitle_job": start_rq_subtitle_job,
            "start_local_video_job": start_rq_video_job,
            "request_job_cancel": request_rq_job_cancel,
        }

    from app.services.local_job_runner import (
        get_task_snapshot,
        get_local_job_worker_status,
        request_job_cancel,
        start_local_highlight_script_job,
        start_local_movie_story_script_job,
        start_local_subtitle_job,
        start_local_video_job,
    )

    return {
        "backend": "local",
        "get_task_snapshot": get_task_snapshot,
        "get_local_job_worker_status": get_local_job_worker_status,
        "start_local_highlight_script_job": start_local_highlight_script_job,
        "start_local_movie_story_script_job": start_local_movie_story_script_job,
        "start_local_subtitle_job": start_local_subtitle_job,
        "start_local_video_job": start_local_video_job,
        "request_job_cancel": request_job_cancel,
    }
