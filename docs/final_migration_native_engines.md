# Final native engine migration

This upgrade moves the former subtitle-first movie-story implementation into:

- `app/services/movie_story/movie_story_native_engine.py`

The old public file now remains as a thin compatibility adapter:

- `app/services/subtitle_first_pipeline.py`

Current backend policy:

- `highlight_edit` auto mode resolves to native.
- `movie_story` auto mode resolves to native.
- legacy engines remain available for explicit compatibility and auto failover.

Do not add new business logic to `subtitle_first_pipeline.py` or `highlight_edit_pipeline.py`.

## Native cleanup follow-up

The primary movie-story implementation name is now `run_movie_story_native_engine` in `app.services.movie_story.movie_story_native_engine`.
The old name `run_subtitle_first_pipeline` remains as a compatibility alias for legacy callers.
