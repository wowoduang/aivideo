# Stage-O: Legacy Engine Boundary

Stage-O introduces:

- `app/services/movie_story/engines.py`

Purpose:

- Centralize all imports of legacy pipeline files.
- Prevent `unified_entry` and `local_job_runner` from depending on legacy pipeline modules directly.
- Prepare for future removal or replacement of:
  - `subtitle_first_pipeline.py`
  - `highlight_edit_pipeline.py`

Allowed dependency direction:

```text
local_job_runner
-> movie_story.unified_entry
-> movie_story.engines
-> legacy-compatible engines
```

Not allowed after Stage-O:

```text
local_job_runner -> subtitle_first_pipeline.py
local_job_runner -> highlight_edit_pipeline.py
unified_entry -> subtitle_first_pipeline.py
unified_entry -> highlight_edit_pipeline.py
```
