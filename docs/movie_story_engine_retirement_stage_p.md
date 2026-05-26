# Stage-P: Engine Retirement Boundary

Stage-P starts the real retirement path for the old large pipeline files.

Before Stage-P:

```text
unified_entry
-> engines
-> subtitle_first_pipeline / highlight_edit_pipeline
```

After Stage-P:

```text
unified_entry
-> engines
-> engine_policy
-> legacy_engines / native_engines
```

## Why this matters

The old files still work, but they are no longer treated as permanent architecture. They are compatibility engines behind `movie_story/legacy_engines.py`.

New code should not import:

- `app.services.subtitle_first_pipeline`
- `app.services.highlight_edit_pipeline`

New code should call:

- `movie_story.unified_entry`
- `movie_story.engines`

## Backend policy

Supported backend labels:

- `auto`
- `legacy`
- `native`

At Stage-P:

- `auto` resolves to `legacy`
- `native` is recorded but safely falls back to `legacy`
- metadata is attached to the payload as `engine_backend_info`

## Next stage

Stage-Q should implement the first native backend, preferably `highlight_edit`, because that chain has already been heavily modularized.
