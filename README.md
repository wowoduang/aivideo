# AIVideoGPT / AIVideo v5

Current backend architecture status:

- `movie_story` is the unified capability layer for movie-story and highlight-edit workflows.
- Frontend product entries can remain separate:
  - movie story
  - highlight recut / 精彩粗剪
- Backend core should converge through:
  - `app/services/movie_story/unified_entry.py`
  - `app/services/movie_story/engines.py`
  - `CompositionPlan` output

Important documents:

- `docs/current_architecture_status.md`
- `docs/movie_story_legacy_engine_stage_o.md`
- `docs/archive/README.md`

Root documentation policy:

- Keep only `README.md` in the repository root.
- Put current architecture and migration documents under `docs/`.
- Put historical reports under `docs/archive/`.
