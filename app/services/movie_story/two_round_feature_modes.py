# -*- coding: utf-8 -*-
from __future__ import annotations

"""
two_round_feature_modes.py

Movie-story 当前可用主流程的明确功能入口。

为什么新增本模块：
- 旧 Native/Legacy movie_story 主流程已经从默认调度中切出。
- 当前要保留两个明确功能，而不是继续让 movie_story_script 进入旧大杂烩：
  1) two_round：只跑 raw_srt 双轮解说链，成本低、速度快。
  2) two_round_visual：第一轮提示词前抽取全片低密度帧和 visual_focus_segments
     详细帧，调用多模态第一轮做全片结构理解，再复用第二轮文本写作链。

生产者：
- app.services.movie_story.unified_entry.run_movie_story_request

消费者：
- app.services.local_job_runner 的 movie_story_script job
- 前端 movie_story_script 结果预览
- 后续剪辑/导出链路

正式产物：
- movie_story_script.json
- movie_story_script_highlights.json
- movie_story_script_highlight_narration_segments.json

注意：
- 本模块不调用旧 Native/Legacy Runtime。
- 本模块不做 fallback；缺少字幕、模型或输出路径就直接报错。
- two_round_visual 不允许假跑 text-only 双轮链；缺视觉配置/抽帧失败必须报错。
"""

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.services.generate_narration_script_clean import _generate_raw_srt_narration_items
from app.services.movie_story.two_round_visual_narration import generate_two_round_visual_narration_items

ProgressCallback = Optional[Callable[[int, str], None]]

__all__ = ["run_movie_story_two_round_feature_mode"]


def run_movie_story_two_round_feature_mode(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
    visual_enabled: bool = False,
) -> Dict[str, Any]:
    """Run the explicit two-round movie-story feature mode."""

    mode = "two_round_visual" if visual_enabled else "two_round"
    output_path = Path(str(output_script_path or request.get("output_script_path") or "").strip())
    if not str(output_path):
        raise ValueError("output_script_path is required for movie_story two_round mode")

    raw_srt_text = _resolve_raw_srt_text(request)
    api_key, base_url, model = _resolve_text_llm_settings(request)
    style = str(request.get("narration_style") or request.get("style") or "general").strip() or "general"

    if not raw_srt_text.strip():
        raise ValueError("raw_srt_text/subtitle_path is required for movie_story two_round mode")

    _progress(progress_callback, 8, "读取原始字幕")
    logger.info("movie_story two_round feature mode started: mode={}, output={}", mode, output_path)

    _progress(progress_callback, 25, "双轮链生成解说")
    visual_metadata: Dict[str, Any] = {}
    if visual_enabled:
        _progress(progress_callback, 32, "构建第一轮多模态视觉证据")
        items, visual_metadata = generate_two_round_visual_narration_items(
            raw_srt_text=raw_srt_text,
            request=request,
            output_dir=output_path.parent,
            text_api_key=api_key,
            text_base_url=base_url,
            text_model=model,
            style=style,
        )
    else:
        items = _generate_raw_srt_narration_items(
            [],
            raw_srt_text=raw_srt_text,
            api_key=api_key,
            base_url=base_url,
            model=model,
            style=style,
        )
    if not isinstance(items, list) or not items:
        raise RuntimeError("two_round narration returned no script items")

    normalized_items = [_normalize_script_item(item, index) for index, item in enumerate(items, start=1)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, normalized_items)

    highlights = _build_highlights(normalized_items)
    narration_segments = _build_highlight_narration_segments(normalized_items)

    highlights_path = Path(str(output_path).replace(".json", "_highlights.json"))
    narration_segments_path = Path(str(output_path).replace(".json", "_highlight_narration_segments.json"))

    _write_json(highlights_path, highlights)
    _write_json(narration_segments_path, narration_segments)

    _progress(progress_callback, 88, "双轮链产物写入完成")
    logger.info(
        "movie_story two_round feature mode completed: items={}, highlights={}, visual_enabled={}",
        len(normalized_items),
        len(highlights),
        visual_enabled,
    )

    return {
        "success": True,
        "movie_story_mode": mode,
        "generation_mode": "raw_srt_two_round_narration",
        "script_items": normalized_items,
        "items": normalized_items,
        "script_path": str(output_path),
        "output_script_path": str(output_path),
        "video_path": str(request.get("video_path") or ""),
        "highlights_path": str(highlights_path),
        "highlight_narration_segments_path": str(narration_segments_path),
        "highlights_count": len(highlights),
        "highlight_narration_segments_count": len(narration_segments),
        "visual_evidence_requested": bool(visual_enabled),
        "two_round_visual_metadata": visual_metadata,
        "warnings": [],
    }


def _resolve_text_llm_settings(request: Dict[str, Any]) -> tuple[str, str, str]:
    """Resolve text LLM settings from request, backend config, or environment."""

    api_key = _first_request_value(
        request,
        ("text_api_key", "api_key", "llm_api_key", "narration_api_key"),
    )
    base_url = _first_request_value(
        request,
        ("text_base_url", "base_url", "llm_base_url", "narration_base_url", "api_base"),
    )
    model = _first_request_value(
        request,
        ("text_model", "model", "llm_model", "narration_model"),
    )

    config_pairs = _collect_project_config_strings()

    if not api_key:
        api_key = _find_config_value(
            config_pairs,
            required=("api", "key"),
            include_any=("text", "llm", "deepseek", "openai", "dashscope", "qwen", "aliyun"),
            exclude_any=("vision", "image", "video", "embedding", "asr", "whisper", "base", "url"),
        )
    if not model:
        model = _find_config_value(
            config_pairs,
            required=("model",),
            include_any=("text", "llm", "deepseek", "openai", "dashscope", "qwen"),
            exclude_any=("vision", "image", "video", "embedding", "asr", "whisper"),
        )

    if not api_key:
        api_key = _first_env(
            (
                "AIVIDEO_TEXT_API_KEY",
                "TEXT_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
                "DASHSCOPE_API_KEY",
                "QWEN_API_KEY",
            )
        )
    if not base_url:
        base_url = _first_env(
            (
                "AIVIDEO_TEXT_BASE_URL",
                "TEXT_BASE_URL",
                "DEEPSEEK_BASE_URL",
                "OPENAI_BASE_URL",
                "DASHSCOPE_BASE_URL",
            )
        )
    base_url = _sanitize_text_base_url_for_model(model, base_url)
    if not model:
        model = _first_env(("AIVIDEO_TEXT_MODEL", "TEXT_MODEL", "LLM_MODEL", "MODEL_NAME"))

    if not api_key:
        raise ValueError(
            "text_api_key is required for movie_story two_round mode; "
            "send text_api_key or configure backend text provider api_key"
        )
    if not model:
        raise ValueError(
            "text_model is required for movie_story two_round mode; "
            "send text_model or configure backend text provider model"
        )

    return api_key, base_url, model


def _first_request_value(request: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(request.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_env(keys: tuple[str, ...]) -> str:
    import os

    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _collect_project_config_strings() -> list[tuple[str, str]]:
    """Collect string config values from app.config.config without printing secrets."""

    try:
        from app.config import config as config_module
    except Exception:
        return []

    import inspect

    pairs: list[tuple[str, str]] = []
    seen: set[int] = set()

    def visit(obj: Any, prefix: str, depth: int) -> None:
        if depth > 5:
            return
        obj_id = id(obj)
        if obj_id in seen:
            return
        seen.add(obj_id)

        if isinstance(obj, (str, int, float, bool)):
            value = str(obj).strip()
            if value:
                pairs.append((prefix.lower(), value))
            return

        if obj is None or inspect.ismodule(obj) or inspect.isfunction(obj) or inspect.isclass(obj):
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                key_text = str(key).strip()
                if key_text:
                    visit(value, f"{prefix}.{key_text}" if prefix else key_text, depth + 1)
            return

        if isinstance(obj, (list, tuple)):
            for index, value in enumerate(obj[:100]):
                visit(value, f"{prefix}.{index}", depth + 1)
            return

        data = getattr(obj, "__dict__", None)
        if isinstance(data, dict):
            for key, value in data.items():
                if not str(key).startswith("_"):
                    visit(value, f"{prefix}.{key}" if prefix else str(key), depth + 1)

    for name in dir(config_module):
        if name.startswith("_") or name in {"logger", "Path", "os", "toml", "json"}:
            continue
        try:
            visit(getattr(config_module, name), name, 0)
        except Exception:
            continue

    return pairs


def _sanitize_text_base_url_for_model(model: str, base_url: str) -> str:
    """Prevent provider/base-url cross wiring in the text LLM config.

    The backend config may contain several provider endpoints.  A DeepSeek
    model must not be called through DashScope compatible-mode base_url; that
    combination makes LiteLLM set DEEPSEEK_API_KEY while sending the request to
    DashScope, which produces invalid_api_key.
    """

    normalized_model = str(model or "").strip().lower()
    normalized_base = str(base_url or "").strip()
    base_lower = normalized_base.lower()

    if normalized_model.startswith("deepseek/") and "dashscope.aliyuncs.com" in base_lower:
        raise ValueError(
            "incompatible text LLM config: model is deepseek/* but base_url points to DashScope; "
            "clear text_base_url/DASHSCOPE_BASE_URL for DeepSeek, or use a DashScope/Qwen model name"
        )

    return normalized_base

def _find_config_value(
    pairs: list[tuple[str, str]],
    *,
    required: tuple[str, ...],
    include_any: tuple[str, ...],
    exclude_any: tuple[str, ...],
) -> str:
    for key, value in pairs:
        compact_key = key.replace("-", "_").replace(".", "_").lower()
        if required and not all(token in compact_key for token in required):
            continue
        if include_any and not any(token in compact_key for token in include_any):
            continue
        if exclude_any and any(token in compact_key for token in exclude_any):
            continue
        if value:
            return value
    return ""

def _resolve_raw_srt_text(request: Dict[str, Any]) -> str:
    """Resolve raw SRT text from explicit request text or subtitle_path."""

    for key in ("raw_srt_text", "raw_subtitle_text", "subtitle_text"):
        value = str(request.get(key) or "").strip()
        if value:
            return value

    subtitle_path = str(request.get("subtitle_path") or request.get("raw_subtitle_path") or "").strip()
    if not subtitle_path:
        raise ValueError("subtitle_path is required when raw_srt_text is not provided")

    path = Path(subtitle_path)
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"subtitle file is empty: {path}")
    return text


def _normalize_script_item(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise TypeError(f"two_round script item must be dict: index={index}")

    normalized = dict(item)
    normalized.setdefault("id", f"script_{index:03d}")
    normalized.setdefault("raw_srt_story_order", index)
    normalized.setdefault("generation_mode", "raw_srt_two_round_narration")
    normalized.setdefault("clip_match_rule", "raw_srt_time_range")

    start = _extract_start_seconds(normalized)
    end = _extract_end_seconds(normalized)
    if end <= start:
        raise ValueError(f"invalid script item time range: index={index}, start={start}, end={end}")

    normalized["start"] = round(start, 3)
    normalized["end"] = round(end, 3)
    normalized["start_time"] = _format_mmss(start)
    normalized["end_time"] = _format_mmss(end)
    normalized.setdefault("timestamp", f"{_format_mmss(start)}-{_format_mmss(end)}")

    narration = str(normalized.get("narration") or normalized.get("text") or "").strip()
    if not narration:
        raise ValueError(f"empty narration in two_round script item: index={index}")
    normalized["narration"] = narration
    normalized.setdefault("text", narration)

    return normalized


def _build_highlights(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    highlights: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        highlight_id = f"highlight_{index:03d}"
        start = float(item["start"])
        end = float(item["end"])
        title = str(item.get("section_title") or item.get("title") or f"片段 {index}").strip()
        narration = str(item.get("narration") or item.get("text") or "").strip()
        highlights.append(
            {
                "id": highlight_id,
                "highlight_id": highlight_id,
                "segment_id": highlight_id,
                "source_script_id": item.get("id"),
                "title": title,
                "start": round(start, 3),
                "end": round(end, 3),
                "start_time": _format_mmss(start),
                "end_time": _format_mmss(end),
                "duration": round(end - start, 3),
                "timestamp": f"{_format_mmss(start)}-{_format_mmss(end)}",
                "narration": narration,
                "selected": True,
                "generation_mode": "raw_srt_two_round_narration",
                "producer": "two_round_feature_modes",
            }
        )
    return highlights


def _build_highlight_narration_segments(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        highlight_id = f"highlight_{index:03d}"
        start = float(item["start"])
        end = float(item["end"])
        narration = str(item.get("narration") or item.get("text") or "").strip()
        segments.append(
            {
                "id": highlight_id,
                "highlight_id": highlight_id,
                "segment_id": highlight_id,
                "source_script_id": item.get("id"),
                "start": round(start, 3),
                "end": round(end, 3),
                "start_time": _format_mmss(start),
                "end_time": _format_mmss(end),
                "duration": round(end - start, 3),
                "timestamp": f"{_format_mmss(start)}-{_format_mmss(end)}",
                "narration": narration,
                "text": narration,
                "source_text": str(item.get("source_text") or item.get("subtitle_text") or "").strip(),
                "generation_mode": "raw_srt_two_round_narration",
                "producer": "two_round_feature_modes",
            }
        )
    return segments


def _extract_start_seconds(item: Dict[str, Any]) -> float:
    for key in ("start", "raw_srt_source_start", "raw_srt_original_start", "raw_srt_declared_start", "clip_start"):
        if key in item and item.get(key) not in (None, ""):
            return _to_seconds(item.get(key))
    timestamp = str(item.get("timestamp") or item.get("raw_srt_source_timestamp") or "").strip()
    parsed = _parse_timestamp_range(timestamp)
    if parsed:
        return parsed[0]
    raise ValueError(f"script item missing start time: {item.get('id')}")


def _extract_end_seconds(item: Dict[str, Any]) -> float:
    for key in ("end", "raw_srt_source_end", "raw_srt_original_end", "raw_srt_declared_end", "clip_end"):
        if key in item and item.get(key) not in (None, ""):
            return _to_seconds(item.get(key))
    timestamp = str(item.get("timestamp") or item.get("raw_srt_source_timestamp") or "").strip()
    parsed = _parse_timestamp_range(timestamp)
    if parsed:
        return parsed[1]
    raise ValueError(f"script item missing end time: {item.get('id')}")


def _parse_timestamp_range(value: str) -> tuple[float, float] | None:
    if not value:
        return None
    parts = re.split(r"\s*[-~—–]\s*", value.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    return (_to_seconds(parts[0]), _to_seconds(parts[1]))


def _to_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    pieces = text.replace(",", ".").split(":")
    if len(pieces) == 2:
        minutes = float(pieces[0])
        seconds = float(pieces[1])
        return minutes * 60.0 + seconds
    if len(pieces) == 3:
        hours = float(pieces[0])
        minutes = float(pieces[1])
        seconds = float(pieces[2])
        return hours * 3600.0 + minutes * 60.0 + seconds
    raise ValueError(f"unsupported time value: {value!r}")


def _format_mmss(seconds: float) -> str:
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    sec = total - minutes * 60
    return f"{minutes:02d}:{sec:05.2f}"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _progress(progress_callback: ProgressCallback, progress: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(progress, message)
