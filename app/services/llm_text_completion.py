from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Optional

from loguru import logger

try:
    import requests
except Exception:  # pragma: no cover
    requests = None



def _run_async_safely(coro, timeout: Optional[int] = None):
    async def _with_timeout():
        if timeout and timeout > 0:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_with_timeout())

    def run_in_new_loop():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_with_timeout())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run_in_new_loop).result(timeout=(timeout + 5) if timeout else None)


def _record_llm_usage_safely(*, prompt: str, completion: str, model: str, base_url: str, log_label: str, usage: Optional[dict] = None) -> None:
    try:
        from app.services import runtime_context, usage_meter

        owner = runtime_context.current_owner()
        if not owner:
            return
        usage_data = usage_meter.extract_llm_token_usage(usage)
        usage_meter.record_llm_usage(
            owner=owner,
            provider=(base_url or "litellm"),
            model=model,
            prompt_chars=len(prompt or ""),
            completion_chars=len(completion or ""),
            prompt_tokens=usage_data.get("prompt_tokens"),
            completion_tokens=usage_data.get("completion_tokens"),
            total_tokens=usage_data.get("total_tokens"),
            task_id=runtime_context.current_task_id(),
            project_id=runtime_context.current_project_id(),
            label=log_label,
        )
    except Exception:
        return


def call_text_chat_completion(
    prompt: str,
    *,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    timeout: int = 120,
    log_label: str = "LLM",
) -> str:
    if not (api_key and model):
        return ""

    clean_base_url = str(base_url or "").strip()
    # RAW_SRT_V6_SKIP_DIRECT_HTTP_FOR_LITELLM_MODEL
    # LiteLLM 风格模型名通常是 provider/model，例如 deepseek/deepseek-chat。
    # 这种模型名直接打原厂 /chat/completions 容易 400，应该直接走 LiteLLM provider。
    direct_http_allowed = bool(requests and clean_base_url and "/" not in str(model or ""))
    if requests and clean_base_url and not direct_http_allowed:
        logger.debug("{} 跳过直连 HTTP，直接使用 LiteLLM provider: model={}", log_label, model)

    if direct_http_allowed:
        url = clean_base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            completion = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
            _record_llm_usage_safely(prompt=prompt, completion=completion, model=model, base_url=clean_base_url, log_label=log_label, usage=usage)
            return completion
        except Exception as exc:
            logger.warning("{} HTTP 调用失败，尝试回退 LiteLLM: {}", log_label, exc)

    try:
        from app.services.llm.litellm_provider import LiteLLMTextProvider

        provider = LiteLLMTextProvider(
            api_key=api_key,
            model_name=model,
            base_url=clean_base_url or None,
        )
        completion = _run_async_safely(
            provider.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            ),
            timeout=timeout,
        ).strip()
        _record_llm_usage_safely(prompt=prompt, completion=completion, model=model, base_url=clean_base_url or "litellm", log_label=log_label)
        return completion
    except Exception as exc:
        logger.warning("{} LiteLLM 调用失败，回退规则路径: {}", log_label, exc)
        return ""
