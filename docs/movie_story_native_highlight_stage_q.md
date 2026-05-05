# Stage-Q: Native Highlight Edit Backend

Stage-Q makes `highlight_edit` / “精彩粗剪” the first real native backend in
`movie_story`.

Before Stage-Q:

```text
unified_entry
-> engines
-> engine_policy
-> legacy_engines
-> highlight_edit_pipeline.py
```

After Stage-Q for highlight-edit requests:

```text
unified_entry
-> engines
-> engine_policy
-> native_engines
-> highlight_native_engine
-> movie_story highlight_edit_* modules
```

## Policy

- `highlight_edit` native readiness is now `true`.
- `auto` selects native for highlight-edit.
- `movie_story` remains legacy until its native parity path is implemented.
- legacy highlight-edit remains available through `engine_backend=legacy`.

## Why highlight-edit first

The highlight-edit pipeline was already split across:

- `highlight_edit_candidates.py`
- `highlight_edit_selection.py`
- `highlight_edit_composition.py`
- `highlight_edit_context.py`
- `highlight_edit_outputs.py`

That makes it the safest first native backend.

## Next stage

Stage-R should either:

1. Make `highlight_edit_pipeline.py` a thin adapter that calls native directly, or
2. Start the native `movie_story` narration backend.
