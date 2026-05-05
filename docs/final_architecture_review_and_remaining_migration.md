# Final Architecture Review and Remaining Migration Notes

This document records the post-migration architecture status after moving the
old subtitle-first movie-story chain and highlight-edit chain into the
`movie_story` native engine layer.

## Current backend shape

```text
front-end entries
  movie-story-script
  highlight-script
        |
        v
movie_story.unified_entry
        |
        v
movie_story.engines
        |
        +-- native_engines
        |     +-- movie_story_native_engine
        |     +-- highlight_native_engine
        |
        +-- legacy_engines
              +-- subtitle_first_pipeline fallback
              +-- highlight_edit_pipeline fallback
```

## What was kept from the old repository

- Subtitle-first story understanding and narration generation were preserved,
  but moved behind `movie_story_native_engine`.
- Highlight recut and CompositionPlan generation were preserved, but moved
  behind `highlight_native_engine` and `movie_story/highlight_edit_*` modules.
- Legacy engines remain available for compatibility and safe rollback.
- Native engine metadata is attached to every engine payload through
  `engine_backend_info`.

## New guardrails

- `engine_status.py` exposes backend readiness and policy decisions.
- `architecture_guard.py` prevents new direct imports of retired pipeline files.
- `tools/audit_movie_story_native_migration.py` prints an auditable JSON status
  for native readiness and direct legacy import isolation.

## Remaining work after this package

The remaining tasks are operational rather than architectural:

1. Run real video E2E tests for movie story and highlight recut modes.
2. Compare native and legacy outputs on a small sample set.
3. Once parity is accepted, move legacy pipeline files to `app/services/legacy/`
   or remove them.
4. Update frontend labels and API docs to prefer unified modes.
5. Keep `script_items` as compatibility output while renderers converge on
   `CompositionPlan`.
