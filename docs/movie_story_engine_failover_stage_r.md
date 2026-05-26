# Stage-R: Native Engine Failover

Stage-R adds a safety layer for native highlight-edit rollout.

## Policy

- `engine_backend=legacy`: always run legacy.
- `engine_backend=native`: run native and expose native failures.
- `engine_backend=auto`: run native when selected by policy; if native fails, fall back to legacy.

## Why

Stage-Q made highlight-edit the first native backend. Stage-R makes that rollout safer for production by preventing transient native errors from breaking default frontend jobs.

## Important files

- `app/services/movie_story/engine_failover.py`
- `app/services/movie_story/engines.py`
- `tests/test_movie_story_engine_boundary.py`
