# Native Cleanup Final

This cleanup makes the native movie-story name explicit.

- `run_movie_story_native_engine` is now the primary implementation name.
- `run_subtitle_first_pipeline` remains as a backward-compatible alias.
- `subtitle_first_pipeline.py` remains only as a compatibility adapter.
- CompositionPlan metadata now identifies `movie_story_native_engine` as the source pipeline.

Legacy fallback remains isolated in `movie_story/legacy_engines.py`.
