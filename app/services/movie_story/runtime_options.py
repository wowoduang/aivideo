from __future__ import annotations

"""Runtime option helpers for movie-story entry points.

The legacy pipeline mixed request parsing, environment/config lookup and stage
tracing in the main orchestration file.  Keeping these helpers here makes the
compatibility entry point thinner while allowing ``highlight_edit`` or future
movie-story runners to reuse the exact same option semantics.
"""

import os
import time
from typing import Any, Callable, Dict

from loguru import logger

from app.services.movie_story.audit_runtime import (
    _audit_bool_v41,
    _audit_config_value_v41,
    _audit_int_v41,
    _audit_pipeline_marker,
)

try:
    from app.services.llm.runtime_config import get_text_llm_config
except Exception:  # lightweight unit-test stubs may not initialize full config/logger
    def get_text_llm_config() -> Dict[str, str]:
        return {"api_key": "", "base_url": "", "model": ""}


def _resolve_target_minutes(mode: str, overrides: Dict[str, Any]) -> int:
    if overrides.get("target_duration_minutes"):
        try:
            return max(int(overrides["target_duration_minutes"]), 1)
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)
    default_map = {"fast": 5, "balanced": 8, "quality": 10}
    return default_map.get(mode, 8)


def _resolve_visual_mode(visual_mode: str) -> str:
    if visual_mode in {"off", "auto", "boost"}:
        return visual_mode
    return "auto"


def _looks_like_placeholder_secret(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    placeholder_tokens = (
        "your_", "xxx", "xxxx", "changeme", "change_me", "placeholder",
        "example", "test_key", "sk-xxxxx", "sk-xxxx", "请填写", "填入", "替换",
        "<", ">", "none", "null",
    )
    return any(token in text for token in placeholder_tokens)


def _has_real_llm_config(api_key: str, model: str) -> bool:
    return (not _looks_like_placeholder_secret(api_key)) and bool(str(model or "").strip())


def _ensure_llm_ready(api_key: str, base_url: str, model: str) -> tuple:
    """
    Resolve LLM config without failing the whole movie-story flow.

    The pipeline must be able to complete in local/fallback mode.  Older code
    raised when api_key/model was missing, which stopped the run before
    03_story_candidates / 05_selected_highlights / 07_narration_script.
    """
    try:
        cfg = get_text_llm_config()
    except Exception:
        cfg = {}

    final_api_key = str(api_key or "").strip() or str(cfg.get("api_key", "") or "").strip()
    final_model = str(model or "").strip() or str(cfg.get("model", "") or "").strip()
    final_base_url = str(base_url or "").strip() or str(cfg.get("base_url", "") or "").strip()

    if not _has_real_llm_config(final_api_key, final_model):
        logger.warning("LLM 配置不可用或为示例占位值，影视解说进入本地 fallback 闭环模式。")
        return "", "", ""

    return final_api_key, final_base_url, final_model


def _runtime_config_value(key: str, default: Any = None) -> Any:
    return _audit_config_value_v41(key, default)


def _runtime_bool(key: str, env: str, default: bool = False) -> bool:
    return _audit_bool_v41(key, env, default)


def _runtime_int(key: str, env: str, default: int) -> int:
    return _audit_int_v41(key, env, default)


def _movie_story_migration_stage(scene_overrides: Dict[str, Any]) -> str:
    raw = (
        scene_overrides.get("movie_story_migration_stage")
        or os.environ.get("AIVIDEO_MOVIE_STORY_MIGRATION_STAGE")
        or os.environ.get("MOVIE_STORY_MIGRATION_STAGE")
        or _runtime_config_value("movie_story_migration_stage", "production")
        or "production"
    )
    return str(raw or "").strip().lower()


def _resolve_narration_llm_mode(scene_overrides: Dict[str, Any], has_llm: bool) -> str:
    raw = (
        scene_overrides.get("movie_story_narration_llm_mode")
        or scene_overrides.get("narration_llm_mode")
        or os.environ.get("AIVIDEO_MOVIE_STORY_NARRATION_LLM_MODE")
        or os.environ.get("MOVIE_STORY_NARRATION_LLM_MODE")
        or _runtime_config_value("movie_story_narration_llm_mode", "")
        or ""
    )
    migration_stage = _movie_story_migration_stage(scene_overrides)
    mode = str(raw or "").strip().lower()
    aliases = {"off": "disabled", "none": "disabled", "local": "fallback", "safe": "fallback", "默认": "hybrid"}
    mode = aliases.get(mode, mode)
    # Stage-A compatibility can still disable final writing explicitly, but the
    # production baseline must run the restored old understanding chain first
    # and then produce a narration script from that evidence.
    if migration_stage in {"stage_a", "a", "global_local_evidence", "evidence"} and not raw:
        return "disabled"
    if mode not in {"disabled", "fallback", "hybrid", "full", "batch"}:
        mode = "batch" if has_llm else "fallback"
    if not has_llm and mode not in {"disabled", "fallback"}:
        mode = "fallback"
    return mode


def _stage_llm_enabled(scene_overrides: Dict[str, Any], key: str, env: str, default: bool, has_llm: bool) -> bool:
    if not has_llm:
        return False
    if key in scene_overrides:
        return str(scene_overrides.get(key)).strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return _runtime_bool(key, env, default)


def _stage_trace(stage: str, local_vars: Dict[str, Any], status: str, **payload: Any) -> None:
    """Write a small audit marker for an exact pipeline boundary.

    These markers are deliberately cheap: they create manifest/json rows only,
    never clips.  They make a stopped run diagnosable: the last *_before marker
    identifies the concrete function that did not return.
    """
    data = dict(payload or {})
    data["stage"] = stage
    data["status"] = status
    data["wall_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _audit_pipeline_marker(f"{stage}_{status}", data, local_vars)


def _run_traced_stage(stage: str, local_vars: Dict[str, Any], func: Callable[[], Any], **payload: Any) -> Any:
    started = time.monotonic()
    _stage_trace(stage, local_vars, "before", **payload)
    try:
        result = func()
        elapsed = round(time.monotonic() - started, 3)
        extra: Dict[str, Any] = {"elapsed_seconds": elapsed}
        if isinstance(result, list):
            extra["result_count"] = len(result)
        elif isinstance(result, dict):
            extra["result_keys"] = list(result.keys())[:30]
        _stage_trace(stage, local_vars, "after", **payload, **extra)
        return result
    except Exception as exc:
        elapsed = round(time.monotonic() - started, 3)
        _stage_trace(stage, local_vars, "error", **payload, elapsed_seconds=elapsed, error=f"{type(exc).__name__}: {exc}")
        raise
