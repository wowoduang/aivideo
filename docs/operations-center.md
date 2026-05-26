# Operations Center

The operations center is the authenticated UI for local deployment observability.

It is available at `/operations` and combines:

- Job history and current worker status.
- Per-job event logs (`queued`, `running`, progress updates, process start/exit/cancel events).
- Cancel action for queued/running jobs.
- System health checks for workspace, disk, FFmpeg, ASR and TTS configuration.
- Usage summary for uploads, file access, TTS and LLM events.

Backend APIs used by the page:

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/workers/status`
- `GET /api/v1/jobs/{task_id}/events`
- `POST /api/v1/jobs/{task_id}/cancel`
- `GET /api/v1/system/health`
- `GET /api/v1/system/usage`

All endpoints require the normal bearer session token.

## Production queue mode

When `AIVIDEO_JOB_BACKEND=rq` is enabled, the worker status panel reports the
Redis/RQ queue name, availability, queued/running counts and any connection or
missing dependency error. See `docs/production-queue-rq.md` for worker startup.

## Provider-level usage

Usage is grouped by normalized provider keys such as `openai`, `dashscope`,
`edge_tts`, `azure`, `gemini`, `anthropic` and `deepseek`. LLM events prefer
provider token usage when available and fall back to character counts. TTS and
ASR events record provider-specific character/audio-second volume.
