# Production job queue: Redis/RQ

The default job backend remains the local bounded daemon worker pool. It is safe
for local development and single-user installs, but production deployments should
run video/ASR/TTS/LLM jobs outside the FastAPI process.

## Enable RQ backend

Install optional dependencies:

```bash
pip install -r requirements-rq.txt
```

Run Redis, then start the API with:

```bash
export AIVIDEO_JOB_BACKEND=rq
export AIVIDEO_RQ_REDIS_URL=redis://localhost:6379/0
export AIVIDEO_RQ_QUEUE=aivideo_jobs
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Start one or more workers from the same project directory:

```bash
export AIVIDEO_JOB_BACKEND=rq
export AIVIDEO_RQ_REDIS_URL=redis://localhost:6379/0
rq worker aivideo_jobs
```

The API writes `queued` status to SQLite immediately, then enqueues the job.
The worker updates `job_history`, `job_events`, and artifacts as it runs. The API
can still read progress through `/api/v1/jobs`, `/api/v1/jobs/{task_id}`, and
`/api/v1/jobs/{task_id}/events` even though worker process memory is separate.

## Cancellation model

`POST /api/v1/jobs/{task_id}/cancel` records `cancel_requested` in SQLite. RQ can
remove jobs that have not started; running workers exit cooperatively through the
same cancellation checks used by the local runner. FFmpeg/ffprobe subprocesses
that use `run_cancellable()` will be terminated when cancellation is observed.

## Worker status

`GET /api/v1/jobs/workers/status` reports the active backend. With RQ enabled it
includes queue name, Redis URL, queued/running/done counts, and any connection or
missing dependency error.

## Fallback

Unset `AIVIDEO_JOB_BACKEND` or set `AIVIDEO_JOB_BACKEND=local` to return to the
in-process bounded daemon worker pool.
