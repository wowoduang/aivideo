# Current Architecture Status

Stage-O status:

- `movie_story` is the current capability layer for movie-story and highlight-edit features.
- `local_job_runner` should call `movie_story.unified_entry` instead of importing legacy pipelines directly.
- `movie_story.unified_entry` should call `movie_story.engines`.
- `movie_story.engines` is the only compatibility boundary allowed to import:
  - `app.services.subtitle_first_pipeline`
  - `app.services.highlight_edit_pipeline`

Current entry policy:

- Frontend can keep separate product entries:
  - movie story
  - highlight recut / 精彩粗剪
- Backend core should converge into `movie_story` unified entry and `CompositionPlan` output.
- Legacy pipeline files are compatibility engines and should not receive new business logic.

Current output policy:

- `CompositionPlan` is the preferred final output.
- `script_items` remain as compatibility output for older callers.
