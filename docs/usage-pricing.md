# Usage pricing

Usage events are always recorded by volume. Cost estimates are optional and are
configured by deployment environment because model prices, regions and discounts
change frequently.

Set `AIVIDEO_USAGE_PRICES_JSON` to a JSON object whose keys are:

```text
event_type:provider:unit_name
```

Example:

```bash
export AIVIDEO_USAGE_PRICES_JSON='{
  "llm_prompt_tokens:openai:tokens": 0.00000015,
  "llm_completion_tokens:openai:tokens": 0.00000060,
  "tts_characters:azure:characters": 0.000016,
  "asr_audio_seconds:dashscope:seconds": 0.0001
}'
```

Use `*` as a wildcard:

```json
{"llm_total_tokens:*:tokens": 0.0000003}
```

`GET /api/v1/system/usage` returns both usage summaries and pricing status.
