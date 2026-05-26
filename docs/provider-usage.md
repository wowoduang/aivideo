# Provider-level usage accounting

AIVideo records usage events in SQLite `usage_events` so the Operations Center
can show volume and cost signals by provider.

## LLM

The LLM wrappers normalize OpenAI/LiteLLM/Gemini-style usage payloads:

- `prompt_tokens` / `completion_tokens` / `total_tokens`
- `input_tokens` / `output_tokens`
- `prompt_token_count` / `candidates_token_count` / `total_token_count`

When token usage is not available, the system falls back to `llm_prompt` and
`llm_completion` character counts. Provider names are normalized to stable keys
such as `openai`, `dashscope`, `gemini`, `anthropic`, `deepseek`, or `azure`.

## TTS

TTS synthesis records:

- `tts_characters` in `characters`
- `tts_audio_seconds` in `seconds` when media duration probing succeeds

The metadata includes voice name, output size and task/project identifiers when
running inside a job context.

## ASR

ASR/subtitle generation records:

- `asr_audio_seconds` in `seconds`

This is recorded for subtitle jobs and movie-story auto-subtitle generation when
a runtime job context is present.
