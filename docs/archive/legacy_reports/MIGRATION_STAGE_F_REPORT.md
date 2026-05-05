# Migration Stage F Report — Narration Generation Sampling

## Goal
Stage F is the first bounded final-narration test after Stage E understanding writeback has passed. It does not generate a full production script. It samples a tiny number of highlights that have Stage-E global/local writeback and calls the legacy `movie_story_narration/narration_generation` style prompt.

## New artifacts

- `app/services/movie_story/narration_sample.py`
- `tools/run_stage_f_narration_live.py`
- audit stage: `07a_narration_generation_sample_contract`
- verifier support: `--stage stage_f`

## What Stage F checks

- Stage E prerequisite is still passed.
- Stage-F sample rows exist.
- Every sampled row applies Stage-E global writeback and local writeback.
- Every sampled row uses narration intent, story function, and char budget.
- LLM calls are bounded by `--stage-f-max-llm-calls`.
- Generated rows include `narration`, `raw_voice_keep`, `confidence`, and `grounding_notes`.

## Run

```powershell
python tools/run_stage_f_narration_live.py `
  --audit-dir E:\aivideo-v5-workspace\frontend_uploads\video\_movie_story_pipeline_audit_clips\run_xxxxx `
  --max-live-calls 2 `
  --min-results 2 `
  --api-key "你的key" `
  --base-url "https://api.deepseek.com/v1" `
  --model "deepseek-chat"
```

Then verify:

```powershell
python tools/verify_movie_story_migration_stage.py `
  --stage stage_f `
  --audit-dir E:\aivideo-v5-workspace\frontend_uploads\video\_movie_story_pipeline_audit_clips\run_xxxxx `
  --stage-e-max-llm-calls 3 `
  --stage-e-min-global-results 1 `
  --stage-e-min-local-results 2 `
  --stage-f-max-llm-calls 2 `
  --stage-f-min-results 2
```

## Next stage
If Stage F passes, proceed to Stage G: legacy narration validation and safe rewrite contract.
