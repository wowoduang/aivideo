# Migration Stage C Report

## Stage target

Stage C migrates the legacy `movie_story_narration/narration_generation` input contract into the new project **without calling the final LLM**.

This stage does not evaluate final narration text. It verifies that every selected highlight can be transformed into a replayable legacy prompt input package:

- `segment_json`
- `project_context`
- `style`
- `char_budget`
- `global_summary`
- `local_understanding`
- `story_function`
- `selection_reason`
- `narration_intent`

The output stage is:

```text
06b_narration_generation_input_contract
```

## Token policy

Stage C explicitly disables final narration LLM calls:

```json
"llm_call_enabled": false
```

The verifier fails if any replay item enables LLM calls or exceeds the prompt input budget.

## Verification command

```bash
python tools/verify_movie_story_migration_stage.py \
  --stage stage_c \
  --audit-dir <run_dir>
```

Optional budget override:

```bash
python tools/verify_movie_story_migration_stage.py \
  --stage stage_c \
  --audit-dir <run_dir> \
  --max-input-chars 12000
```

## Current validation

Validated with unit tests:

```text
pytest -q tests/test_movie_story_migration_stage_a.py \
          tests/test_movie_story_migration_stage_b.py \
          tests/test_movie_story_migration_stage_c.py
```

Result:

```text
5 passed
```

A replay check was also run using the user's Stage-B audit output. After generating the new Stage-C replay stage from the existing selected highlights, verification returned:

```json
{
  "overall_passed": true,
  "narration_input_pass_rate": 1.0,
  "llm_enabled_count": 0,
  "over_budget_count": 0
}
```

## Next stage

If Stage C passes on the user's fresh run, enter Stage D:

```text
Stage D: legacy global/local LLM understanding quality migration, with sampled/cached LLM calls.
```
