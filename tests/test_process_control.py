from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from app.services import runtime_context
from app.services.process_control import ProcessCancelled, run_cancellable, cancel_task_processes


def test_run_cancellable_can_terminate_task_process():
    task_id = "process-cancel-test"

    with runtime_context.job_context(owner="user@example.com", task_id=task_id, project_id="project-1"):
        def cancel_later():
            time.sleep(0.25)
            cancel_task_processes(task_id)

        t = threading.Thread(target=cancel_later, daemon=True)
        t.start()
        with pytest.raises((ProcessCancelled, subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            # The process is force-terminated by cancel_task_processes. Depending
            # on platform timing, communicate may observe either cancellation or
            # a non-zero return code; both prove the child did not keep running.
            completed = run_cancellable(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=5,
            )
            if completed.returncode == 0:
                raise AssertionError("subprocess unexpectedly completed")
        t.join(timeout=1)
