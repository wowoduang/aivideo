from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections import defaultdict
from typing import Any, Dict, Iterable

from loguru import logger

from app.services import runtime_context


class ProcessCancelled(BaseException):
    """Raised when a task-scoped subprocess is cancelled by the job runner."""


_PROCESS_LOCK = threading.Lock()
_TASK_PROCESSES: dict[str, set[subprocess.Popen]] = defaultdict(set)


def _current_task_id() -> str:
    return str(runtime_context.current_task_id() or "").strip()


def _register(task_id: str, proc: subprocess.Popen) -> None:
    if not task_id:
        return
    with _PROCESS_LOCK:
        _TASK_PROCESSES[task_id].add(proc)


def _unregister(task_id: str, proc: subprocess.Popen) -> None:
    if not task_id:
        return
    with _PROCESS_LOCK:
        procs = _TASK_PROCESSES.get(task_id)
        if not procs:
            return
        procs.discard(proc)
        if not procs:
            _TASK_PROCESSES.pop(task_id, None)


def tracked_process_counts() -> Dict[str, Any]:
    with _PROCESS_LOCK:
        by_task = {task_id: len(procs) for task_id, procs in _TASK_PROCESSES.items() if procs}
    return {"active_processes": sum(by_task.values()), "tasks": by_task}


def _terminate_process(proc: subprocess.Popen, *, grace_seconds: float = 2.0) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt" and getattr(os, "killpg", None):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=max(0.1, float(grace_seconds)))
            return
        except subprocess.TimeoutExpired:
            pass  # IO/队列清理，忽略异常
        if os.name != "nt" and getattr(os, "killpg", None):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        else:
            proc.kill()
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        logger.warning("failed to terminate subprocess pid={} error={}", getattr(proc, "pid", ""), exc)


def cancel_task_processes(task_id: str) -> int:
    """Terminate all subprocesses currently registered for a job task."""

    task_id = str(task_id or "").strip()
    if not task_id:
        return 0
    with _PROCESS_LOCK:
        procs = list(_TASK_PROCESSES.get(task_id, set()))
    for proc in procs:
        _terminate_process(proc)
    return len(procs)




def _command_preview(args: Iterable[str] | str) -> dict[str, Any]:
    if isinstance(args, str):
        parts = args.split()
        return {"executable": parts[0] if parts else args, "argv_preview": args[:240]}
    argv = [str(part) for part in list(args)]
    return {"executable": argv[0] if argv else "", "argv_preview": argv[:10]}


def _record_process_event(event_type: str, *, task_id: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    owner = runtime_context.current_owner()
    if not owner or not task_id:
        return
    try:
        from app.services import job_events

        job_events.record_event(
            owner=owner,
            task_id=task_id,
            project_id=runtime_context.current_project_id(),
            job_type="",
            event_type=event_type,
            status="running" if event_type == "process_start" else event_type,
            progress=0,
            message=message,
            metadata=metadata or {},
        )
    except Exception as exc:  # pragma: no cover - observability must not break work
        logger.debug("failed to record process event for {}: {}", task_id, exc)

def _is_cancel_requested(task_id: str) -> bool:
    if not task_id:
        return False
    try:
        from app.services.local_job_runner import is_cancel_requested

        return bool(is_cancel_requested(task_id))
    except Exception:
        return False


def run_cancellable(args: Iterable[str] | str, **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run-compatible wrapper that cooperates with job cancellation.

    The wrapper registers child processes under the current runtime task id and
    terminates them when /jobs/{task_id}/cancel is requested. It supports the
    subprocess.run kwargs used by the project: check, timeout, capture_output,
    text/universal_newlines, stdout/stderr, cwd/env, encoding/errors and shell.
    """

    check = bool(kwargs.pop("check", False))
    timeout = kwargs.pop("timeout", None)
    capture_output = bool(kwargs.pop("capture_output", False))
    input_data = kwargs.pop("input", None)
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    popen_kwargs = dict(kwargs)
    if os.name != "nt" and "start_new_session" not in popen_kwargs:
        # Avoid preexec_fn because it is unsafe in multi-threaded FastAPI/tests.
        popen_kwargs["start_new_session"] = True

    task_id = _current_task_id()
    if task_id and _is_cancel_requested(task_id):
        raise ProcessCancelled(f"job_cancelled:{task_id}")

    preview = _command_preview(args)
    _record_process_event(
        "process_start",
        task_id=task_id,
        message=f"started {preview.get('executable') or 'subprocess'}",
        metadata=preview,
    )

    start = time.monotonic()
    proc = subprocess.Popen(args, **popen_kwargs)
    _register(task_id, proc)
    stdout = stderr = None
    try:
        while True:
            if task_id and _is_cancel_requested(task_id):
                _terminate_process(proc)
                _record_process_event(
                    "process_cancelled",
                    task_id=task_id,
                    message=f"cancelled {preview.get('executable') or 'subprocess'}",
                    metadata={**preview, "pid": getattr(proc, "pid", None)},
                )
                raise ProcessCancelled(f"job_cancelled:{task_id}")
            wait_timeout = 0.35
            if timeout is not None:
                elapsed = time.monotonic() - start
                remaining = float(timeout) - elapsed
                if remaining <= 0:
                    _terminate_process(proc)
                    stdout, stderr = proc.communicate()
                    raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
                wait_timeout = max(0.05, min(wait_timeout, remaining))
            try:
                stdout, stderr = proc.communicate(input=input_data, timeout=wait_timeout)
                break
            except subprocess.TimeoutExpired:
                input_data = None
                continue
    finally:
        _unregister(task_id, proc)

    completed = subprocess.CompletedProcess(args=args, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    _record_process_event(
        "process_exit",
        task_id=task_id,
        message=f"finished {preview.get('executable') or 'subprocess'} rc={proc.returncode}",
        metadata={**preview, "returncode": proc.returncode, "pid": getattr(proc, "pid", None)},
    )
    if check and completed.returncode:
        raise subprocess.CalledProcessError(
            completed.returncode,
            args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed
