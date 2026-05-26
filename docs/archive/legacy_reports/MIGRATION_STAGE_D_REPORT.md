# Migration Stage D Report: Legacy Global/Local Understanding Quality Sampling

## Stage goal

Stage D migrates the old project's LLM-driven understanding layer in a controlled way. It does **not** generate final narration and does **not** call the final narration LLM.

It verifies that the new project can build bounded, cached prompt payloads for:

- `global_story_context_refine`
- `local_understanding_refine`

These payloads are the controlled re-entry point for the old project's `build_global_summary` and `add_local_understanding` quality logic.

## New audit output

```text
06c_understanding_quality_sample_contract
```

Each item includes:

- `sample_id`
- `request_type`
- `prompt_namespace`
- `prompt_name`
- `llm_call_enabled`
- `llm_cache_key`
- `prompt_payload`
- `payload_chars`
- `max_input_chars`
- `quality_targets`
- `understanding_contract_quality`

## Token policy

By default Stage D spends **zero tokens**:

```text
llm_call_enabled = false
max_llm_calls = 0
```

Optional live sampling can be enabled later with:

```powershell
$env:MOVIE_STORY_STAGE_D_LLM_ENABLED="1"
$env:MOVIE_STORY_STAGE_D_MAX_LIVE_CALLS="3"
$env:MOVIE_STORY_STAGE_D_MAX_LOCAL_SAMPLES="8"
```

Even with live sampling enabled, Stage D only samples understanding prompts. It does not call final narration generation.

## Verification command

```powershell
python tools/verify_movie_story_migration_stage.py `
  --stage stage_d `
  --audit-dir E:\aivideo-v5-workspace\frontend_uploads\video\_movie_story_pipeline_audit_clips\run_xxxxx
```

Default verification expects no token spend. If live sampling is enabled, allow the matching budget:

```powershell
python tools/verify_movie_story_migration_stage.py `
  --stage stage_d `
  --audit-dir E:\aivideo-v5-workspace\frontend_uploads\video\_movie_story_pipeline_audit_clips\run_xxxxx `
  --max-llm-calls 3
```

## Stage D pass criteria

- Stage C prerequisite passed.
- `06c_understanding_quality_sample_contract` exists.
- At least 1 global refine request exists.
- At least 6 local refine samples exist by default.
- All samples have cache keys.
- Prompt input is within budget.
- LLM enabled count does not exceed the configured budget.

## What comes next

After Stage D passes in no-token contract mode, Stage E should enable a very small live sample and verify result quality before any final narration generation is re-enabled.
