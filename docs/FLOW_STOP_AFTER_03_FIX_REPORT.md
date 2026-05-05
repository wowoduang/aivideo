# Flow Stop After 03 Fix Report

## Symptom reproduced from uploaded audit package

The uploaded audit package contains:

- `00c_boundary_summary`
- `01_shot_candidates`
- `02_scene_candidates`
- `03_story_candidates`

It does **not** contain:

- `05_selected_highlights`
- `06_scene_evidence_for_narration`
- `07_narration_script`

This means the run reached story grouping but did not complete the high-light selection and narration stages.

## Root cause

The remaining blocking point was between `03_story_candidates` and `05_selected_highlights`.

Two risky paths existed there:

1. Optional LLM highlight planning could still run when a real text model was configured, creating a large request after `03_story_candidates` and making the job appear stuck.
2. Typed highlight selection had no local safety fallback around the type-pool selector. If the typed selector failed on a real payload, the pipeline could exit before writing `05_selected_highlights`.

## Fixes

### 1. Added guarded highlight planning

`subtitle_first_pipeline.py` now uses `_safe_plan_story_highlights(...)` instead of calling `plan_story_highlights(...)` directly.

Default behavior:

- no blocking LLM highlight planning;
- returns a local fallback plan immediately;
- typed local highlight selection still receives the full evidence list;
- LLM highlight planning only runs when explicitly forced with `movie_story_force_llm_highlight_plan=true`.

### 2. Changed narration default to flow-complete fallback

When an API key exists but no explicit narration mode is set, the pipeline now defaults to:

```toml
movie_story_narration_llm_mode = "fallback"
```

This prevents the next stop from moving to `06/07` because of hybrid narration LLM calls.

To enable quality mode after verifying the flow:

```toml
movie_story_narration_llm_mode = "hybrid"
movie_story_narration_llm_max_segments = 8
```

### 3. Added local typed-highlight fallback

`story_runtime.extract_highlights(...)` now catches typed selector failures and falls back to chronological score-based highlight selection. It still writes `05_selected_highlights` so downstream narration can continue.

## Validation performed

- `py_compile` passed for modified files.
- Existing narration / plot understanding tests passed.
- Replayed the uploaded `02_scene_candidates` manifest through `extract_highlights(...)`; it now produces `05_selected_highlights` locally.

