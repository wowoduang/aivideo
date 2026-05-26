from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_CURRENT_OWNER: ContextVar[str] = ContextVar("aivideo_current_owner", default="")
_CURRENT_TASK_ID: ContextVar[str] = ContextVar("aivideo_current_task_id", default="")
_CURRENT_PROJECT_ID: ContextVar[str] = ContextVar("aivideo_current_project_id", default="")


def current_owner() -> str:
    return str(_CURRENT_OWNER.get() or "").strip().lower()


def current_task_id() -> str:
    return str(_CURRENT_TASK_ID.get() or "").strip()


def current_project_id() -> str:
    return str(_CURRENT_PROJECT_ID.get() or "").strip()


@contextmanager
def job_context(*, owner: str = "", task_id: str = "", project_id: str = "") -> Iterator[None]:
    """Bind user/task metadata to the current job thread.

    Expensive lower-level services such as LLM, ASR, TTS, or file generation
    often do not receive the authenticated user explicitly. The local job
    runner sets this context once per worker thread so those services can record
    usage/cost events without threading owner_email through every legacy call.
    """

    owner_token = _CURRENT_OWNER.set(str(owner or "").strip().lower())
    task_token = _CURRENT_TASK_ID.set(str(task_id or "").strip())
    project_token = _CURRENT_PROJECT_ID.set(str(project_id or "").strip())
    try:
        yield
    finally:
        _CURRENT_PROJECT_ID.reset(project_token)
        _CURRENT_TASK_ID.reset(task_token)
        _CURRENT_OWNER.reset(owner_token)
