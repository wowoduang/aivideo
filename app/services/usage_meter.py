from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services import metadata_db, usage_pricing


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _owner_for_db(email: str) -> str | None:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    try:
        row = metadata_db.fetch_one("SELECT email FROM users WHERE email = ?", (normalized,))
        return normalized if row else None
    except Exception:
        return None



def normalize_provider(provider: str = "", *, model: str = "", base_url: str = "", kind: str = "") -> str:
    """Return a stable provider key for usage/cost aggregation."""

    raw = str(provider or "").strip().lower()
    model_l = str(model or "").strip().lower()
    base = str(base_url or "").strip().lower()
    text = " ".join(part for part in [raw, model_l, base] if part)
    if "dashscope" in text or "aliyuncs" in text or "qwen" in model_l or "bailian" in text:
        return "dashscope"
    if "openai" in text or "api.openai.com" in text or model_l.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if "anthropic" in text or "claude" in model_l:
        return "anthropic"
    if "gemini" in text or "google" in text:
        return "gemini"
    if "deepseek" in text:
        return "deepseek"
    if "azure" in text:
        return "azure"
    if "edge" in text:
        return "edge_tts" if kind == "tts" else "edge"
    if raw:
        return raw.replace(" ", "_")
    if model_l:
        return model_l.split("/", 1)[0] if "/" in model_l else model_l
    return kind or "unknown"



def extract_llm_token_usage(usage: Any) -> Dict[str, int | None]:
    """Normalize token usage shapes returned by OpenAI/LiteLLM/Gemini/etc."""

    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    data: Dict[str, Any]
    if isinstance(usage, dict):
        data = usage
    else:
        data = {}
        for key in [
            "prompt_tokens", "completion_tokens", "total_tokens",
            "input_tokens", "output_tokens",
            "prompt_token_count", "candidates_token_count", "total_token_count",
        ]:
            try:
                value = getattr(usage, key)
            except Exception:
                value = None
            if value is not None:
                data[key] = value
    prompt = data.get("prompt_tokens", data.get("input_tokens", data.get("prompt_token_count")))
    completion = data.get("completion_tokens", data.get("output_tokens", data.get("candidates_token_count")))
    total = data.get("total_tokens", data.get("total_token_count"))
    try:
        prompt_i = int(prompt) if prompt is not None else None
    except (TypeError, ValueError):
        prompt_i = None
    try:
        completion_i = int(completion) if completion is not None else None
    except (TypeError, ValueError):
        completion_i = None
    try:
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_i = None
    if total_i is None and prompt_i is not None and completion_i is not None:
        total_i = prompt_i + completion_i
    return {"prompt_tokens": prompt_i, "completion_tokens": completion_i, "total_tokens": total_i}


def record_event(
    *,
    owner: str,
    event_type: str,
    provider: str = "",
    units: int = 0,
    unit_name: str = "count",
    cost_estimate: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = {
        "id": uuid4().hex,
        "owner": _normalize_email(owner),
        "event_type": str(event_type or "event"),
        "provider": str(provider or ""),
        "units": int(units or 0),
        "unit_name": str(unit_name or "count"),
        "cost_estimate": float(cost_estimate or 0.0),
        "metadata": metadata or {},
        "created_at": _now_iso(),
    }
    if not item["cost_estimate"]:
        item["cost_estimate"] = usage_pricing.estimate_cost(
            event_type=item["event_type"],
            provider=item["provider"],
            unit_name=item["unit_name"],
            units=item["units"],
        )
    owner_for_db = _owner_for_db(item["owner"])
    metadata_db.execute(
        """
        INSERT INTO usage_events(
            id, owner_email, event_type, provider, units, unit_name,
            cost_estimate, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"], owner_for_db, item["event_type"], item["provider"],
            item["units"], item["unit_name"], item["cost_estimate"],
            metadata_db.json_dumps(item["metadata"]), item["created_at"],
        ),
    )
    return item


def summarize_usage(owner: str, *, limit: int = 20) -> Dict[str, Any]:
    normalized = _normalize_email(owner)
    rows = metadata_db.fetch_all(
        """
        SELECT event_type, provider, unit_name, COUNT(*) AS event_count,
               SUM(units) AS total_units, SUM(cost_estimate) AS total_cost
        FROM usage_events
        WHERE owner_email = ?
        GROUP BY event_type, provider, unit_name
        ORDER BY event_type, provider, unit_name
        """,
        (normalized,),
    )
    recent_rows = metadata_db.fetch_all(
        """
        SELECT * FROM usage_events
        WHERE owner_email = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (normalized, max(1, int(limit or 20))),
    )
    summary: List[Dict[str, Any]] = []
    for row in rows:
        summary.append({
            "event_type": row["event_type"],
            "provider": row["provider"] or "",
            "unit_name": row["unit_name"] or "count",
            "event_count": int(row["event_count"] or 0),
            "total_units": int(row["total_units"] or 0),
            "total_cost": float(row["total_cost"] or 0.0),
        })
    recent: List[Dict[str, Any]] = []
    for row in recent_rows:
        recent.append({
            "id": row["id"],
            "event_type": row["event_type"],
            "provider": row["provider"] or "",
            "units": int(row["units"] or 0),
            "unit_name": row["unit_name"] or "count",
            "cost_estimate": float(row["cost_estimate"] or 0.0),
            "metadata": metadata_db.json_loads(row["metadata_json"], {}),
            "created_at": row["created_at"],
        })
    return {"summary": summary, "recent": recent, "pricing": usage_pricing.pricing_status()}


def record_llm_usage(
    *,
    owner: str,
    provider: str = "",
    model: str = "",
    prompt_chars: int = 0,
    completion_chars: int = 0,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    task_id: str = "",
    project_id: str = "",
    label: str = "",
) -> None:
    """Record LLM usage.

    Provider token metadata is recorded when available; otherwise we keep the
    character-based estimate used by legacy call paths. This lets the product
    expose useful cost/volume information before every provider has first-class
    pricing support.
    """

    normalized = _normalize_email(owner)
    if not normalized:
        return
    provider_name = normalize_provider(provider, model=model, kind="llm")
    base_metadata = {
        "model": model,
        "raw_provider": provider,
        "task_id": task_id,
        "project_id": project_id,
        "label": label,
    }

    if prompt_tokens is not None:
        record_event(
            owner=normalized,
            event_type="llm_prompt_tokens",
            provider=provider_name,
            units=max(0, int(prompt_tokens or 0)),
            unit_name="tokens",
            metadata=base_metadata,
        )
    else:
        record_event(
            owner=normalized,
            event_type="llm_prompt",
            provider=provider_name,
            units=max(0, int(prompt_chars or 0)),
            unit_name="chars",
            metadata=base_metadata,
        )

    if completion_tokens is not None:
        record_event(
            owner=normalized,
            event_type="llm_completion_tokens",
            provider=provider_name,
            units=max(0, int(completion_tokens or 0)),
            unit_name="tokens",
            metadata=base_metadata,
        )
    else:
        record_event(
            owner=normalized,
            event_type="llm_completion",
            provider=provider_name,
            units=max(0, int(completion_chars or 0)),
            unit_name="chars",
            metadata=base_metadata,
        )

    if total_tokens is not None:
        record_event(
            owner=normalized,
            event_type="llm_total_tokens",
            provider=provider_name,
            units=max(0, int(total_tokens or 0)),
            unit_name="tokens",
            metadata=base_metadata,
        )



def record_tts_usage(
    *,
    owner: str,
    provider: str = "",
    voice_name: str = "",
    characters: int = 0,
    audio_bytes: int = 0,
    audio_seconds: float | None = None,
    task_id: str = "",
    project_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    normalized = _normalize_email(owner)
    if not normalized:
        return
    provider_name = normalize_provider(provider, kind="tts")
    meta = {
        "voice_name": voice_name,
        "task_id": task_id,
        "project_id": project_id,
        "output_bytes": int(audio_bytes or 0),
        **(metadata or {}),
    }
    record_event(
        owner=normalized,
        event_type="tts_characters",
        provider=provider_name,
        units=max(0, int(characters or 0)),
        unit_name="characters",
        metadata=meta,
    )
    if audio_seconds is not None and float(audio_seconds or 0) > 0:
        record_event(
            owner=normalized,
            event_type="tts_audio_seconds",
            provider=provider_name,
            units=max(0, int(round(float(audio_seconds or 0)))) ,
            unit_name="seconds",
            metadata=meta,
        )


def record_asr_usage(
    *,
    owner: str,
    provider: str = "",
    model: str = "",
    audio_seconds: float = 0.0,
    task_id: str = "",
    project_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    normalized = _normalize_email(owner)
    if not normalized:
        return
    provider_name = normalize_provider(provider, model=model, kind="asr")
    meta = {
        "model": model,
        "raw_provider": provider,
        "task_id": task_id,
        "project_id": project_id,
        **(metadata or {}),
    }
    seconds = max(0, int(round(float(audio_seconds or 0.0))))
    record_event(
        owner=normalized,
        event_type="asr_audio_seconds",
        provider=provider_name,
        units=seconds,
        unit_name="seconds",
        metadata=meta,
    )
