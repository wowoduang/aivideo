# Migration Stage B Report

## Stage goal

Stage B migrates the old project's story-aware highlight planning contract into the new project without calling the final narration LLM.

This stage verifies that selected highlights are no longer shallow time/text rows. Every selected highlight must carry:

- `story_role`
- `selection_reason`
- `score_breakdown`
- `source_scene_ids`
- `narration_generation_input`
- `narration_intent`
- `_global_summary`

## Why this matters

The old project did not send raw subtitle snippets directly to the narration writer. It first decided why a clip was worth narrating and what story role it should play. Stage B restores this planning layer before Stage C reconnects the legacy narration prompt.

## New files

- `app/services/movie_story/highlight_planning.py`
- `tests/test_movie_story_migration_stage_b.py`

## Modified files

- `app/services/movie_story/story_runtime.py`
- `tools/verify_movie_story_migration_stage.py`

## New audit stage

- `05b_highlight_planning_contract`

## Verifier

Run:

```bash
python tools/verify_movie_story_migration_stage.py \
  --stage stage_b \
  --audit-dir /path/to/_movie_story_pipeline_audit_clips/run_xxxxx
```

## Acceptance criteria

Stage B passes only when:

1. Stage A passes.
2. `05b_highlight_planning_contract` exists.
3. `06_scene_evidence_for_narration` still passes Stage A rich evidence contract.
4. At least 90% of planned highlights pass the Stage-B contract.
5. Selected highlights cover at least 3 highlight types.
6. Selected highlights cover at least 3 story-arc roles.

## Token policy

Stage B does not call the final LLM writer. It only prepares and verifies the structured input that Stage C will replay into the legacy narration_generation prompt.

## Local validation performed

- `python -m compileall -q app/services/movie_story tools/verify_movie_story_migration_stage.py`
- `pytest -q tests/test_movie_story_migration_stage_a.py tests/test_movie_story_migration_stage_b.py`
- Replayed the user's latest Stage-A audit package: Stage B failed before patch because `story_role`, `selection_reason`, `score_breakdown`, `narration_generation_input`, and arc roles were missing.
- Replayed the same audit after Stage-B enrichment: 32/32 highlights passed, type_count=7, arc_count=4.

## Next stage

Stage C: legacy `narration_generation` prompt input replay and disabled-final-LLM contract verification.
