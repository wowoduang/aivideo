# -*- coding: utf-8 -*-
from __future__ import annotations

"""
unified_entry.py

统一前端编辑入口。负责把前端 movie_story / highlight 请求路由到当前正式主流程。

主线约束：
- movie_story 仅允许 two_round / two_round_visual
- native / legacy / subtitle_first_pipeline 不能作为入口也不能作为 fallback
- highlight 产品链保留独立边界，不与 movie_story 主线混用
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.unified_entry",
    "entry_points": [
        "run_unified_edit_request",
        "run_movie_story_request",
        "run_highlight_request",
    ],
    "called_by": [
        "app.services.local_job_runner",
        "app.api.routers.jobs",
    ],
    "decisions": [
        "2026-05: movie_story_script 主流程只允许 two_round / two_round_visual；旧 native/legacy 不再作为主流程或 fallback。",
        "2026-05: highlight_edit 产品链仍通过 run_highlight_edit_engine 路由，和 movie_story_script 主流程分离。",
        "2026-10: 在统一入口增加强制 mode guard，禁止绕过主线 or 混入 legacy fallback。",
    ],
    "pending": [
        "长视频拆多个短视频产品链稳定后，在此处增加独立显式入口，不能复用旧 native/legacy movie_story。",
        "legacy/native 中仍有价值的确定性模块迁移完成后，将旧目录移入项目回收站。",
        "继续补充入口层 contract 校验，确保所有调用方都遵守 two_round / two_round_visual 主线。",
    ],
    "ai_constraints": [
        "禁止恢复 old native/legacy movie_story 主流程。",
        "禁止把 two_round_visual 缺配置时降级到 two_round。",
        "禁止在统一入口中出现 fallback / silent downgrade。",
        "禁止修改基础双轮链和视觉增强链的两轮提示词内容，除非用户明确要求。",
    ],
}

import os
from typing import Any, Callable, Dict, Optional

from loguru import logger

from app.services.movie_story.edit_modes import (
    ENTRY_HIGHLIGHT_SCRIPT,
    ENTRY_MOVIE_STORY_SCRIPT,
    RAW_HIGHLIGHT,
    engine_mode_for_highlight,
    resolve_unified_mode,
)
from app.services.movie_story.edit_result import UnifiedEditResult
from app.services.highlight_edit_pipeline import run_highlight_edit_pipeline
from app.services.movie_story.two_round_feature_modes import run_movie_story_two_round_feature_mode

ProgressCallback = Optional[Callable[[int, str], None]]

_ALLOWED_MOVIE_STORY_MODES = {"two_round", "two_round_visual"}
_FORBIDDEN_MOVIE_STORY_MODES = {
    "native",
    "legacy",
    "native_runtime",
    "legacy_understanding",
    "subtitle_first_pipeline",
    "plot_first_pipeline",
}


def movie_story_scene_overrides_from_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve advanced movie-story controls at the unified API boundary."""

    overrides: Dict[str, Any] = {
        "target_duration_minutes": int(request.get("target_duration_minutes", 8) or 8),
        "narrative_strategy": str(request.get("narrative_strategy", "chronological") or "chronological"),
        "accuracy_priority": str(request.get("accuracy_priority", "high") or "high"),
        "highlight_only": bool(request.get("highlight_only", False)),
        "highlight_selectivity": str(request.get("highlight_selectivity", "balanced") or "balanced"),
        "video_title": str(request.get("video_theme", "") or request.get("video_title", "") or ""),
        "short_name": str(request.get("video_theme", "") or request.get("video_title", "") or ""),
        "temperature": float(request.get("temperature", 0.7) or 0.7),
        "prologue_strategy": str(request.get("prologue_strategy", "speech_first") or "speech_first"),
        "manual_prologue_end_time": str(request.get("manual_prologue_end_time", "") or ""),
        "movie_story_strategy": str(request.get("movie_story_strategy", "") or ""),
        "skip_llm": bool(request.get("skip_llm", False)),
    }
    passthrough_keys = [
        "movie_story_narration_llm_mode",
        "narration_llm_mode",
        "movie_story_narration_llm_max_segments",
        "movie_story_enable_global_llm",
        "movie_story_enable_segment_llm",
        "movie_story_enable_story_validation_llm",
        "movie_story_enable_highlight_plan_llm",
        "movie_story_enable_narration_validation_llm",
        "movie_story_disable_llm_highlight_plan",
        "movie_story_highlight_plan_max_candidates",
        "movie_story_typed_selector_error_policy",
        "movie_story_audit_export_clips",
        "movie_story_audit_keep_runs",
        "movie_story_audit_keep_stages",
        "movie_story_audit_include_legacy_stages",
        "movie_story_audit_clip_stages",
        "movie_story_audit_max_clips_per_stage",
        "boundary_merge_window_sec",
        "clip_match_tolerance_seconds",
        "scene_threshold",
        "min_scene_len",
        "skip_llm",
    ]
    for key in passthrough_keys:
        if key in request and request.get(key) is not None:
            overrides[key] = request.get(key)
    return overrides


def _validate_mainline_movie_story_mode(mode: str) -> str:
    """Reject legacy/native movie_story mode values before any dispatch."""

    normalized = str(mode or "").strip().lower()
    if not normalized:
        return "two_round"
    if normalized in _FORBIDDEN_MOVIE_STORY_MODES:
        raise RuntimeError(
            "movie_story mainline mode is forbidden: "
            f"{normalized}. use two_round or two_round_visual only; "
            "legacy/native fallback is disabled."
        )
    if normalized not in _ALLOWED_MOVIE_STORY_MODES:
        raise ValueError(f"unsupported_movie_story_mode:{normalized}")
    return normalized


def run_unified_edit_request(
    *,
    entry: str,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    """Run a front-end edit request through one normalized movie-story entry layer."""

    mode_info = resolve_unified_mode(entry, request)
    if mode_info.entry == ENTRY_MOVIE_STORY_SCRIPT:
        mode = _validate_mainline_movie_story_mode(mode_info.mode)
        logger.info(
            "unified edit request accepted: entry={} mode={} mainline_only=true",
            mode_info.entry,
            mode,
        )
    else:
        logger.info("unified edit request: entry={} mode={}", mode_info.entry, mode_info.mode)

    if mode_info.entry == ENTRY_MOVIE_STORY_SCRIPT:
        payload = run_movie_story_request(
            request=request,
            progress_callback=progress_callback,
            output_script_path=output_script_path,
        )
    elif mode_info.entry == ENTRY_HIGHLIGHT_SCRIPT:
        payload = run_highlight_request(
            request=request,
            progress_callback=progress_callback,
        )
    else:
        payload = {
            "success": False,
            "error": f"unsupported_unified_entry:{mode_info.entry}",
            "script_items": [],
            "warnings": [],
        }

    result = UnifiedEditResult.from_payload(entry=mode_info.entry, mode=mode_info.mode, payload=payload)
    normalized = result.to_payload()
    normalized.setdefault("unified_mode_info", mode_info.as_dict())
    return normalized


def run_highlight_request(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
) -> Dict[str, Any]:
    """Run the highlight edit product path through its separate engine boundary."""

    mode_info = resolve_unified_mode(ENTRY_HIGHLIGHT_SCRIPT, request)
    prefer_raw_audio = bool(request.get("prefer_raw_audio", True)) or mode_info.mode == RAW_HIGHLIGHT
    return run_highlight_edit_pipeline(
        video_path=str(request.get("video_path", "") or ""),
        mode=engine_mode_for_highlight(mode_info.mode),
        target_duration_seconds=int(request.get("target_duration_seconds", 480) or 480),
        movie_title=str(request.get("movie_title", "") or ""),
        highlight_profile=str(request.get("highlight_profile", "auto") or "auto"),
        subtitle_path=str(request.get("subtitle_path", "") or ""),
        narration_text=str(request.get("narration_text", "") or ""),
        narration_audio_path=str(request.get("narration_audio_path", "") or ""),
        prefer_raw_audio=prefer_raw_audio,
        visual_mode="off" if bool(request.get("skip_llm", False)) else str(request.get("visual_mode", "auto") or "auto"),
        regenerate_subtitle=bool(request.get("regenerate_subtitle", False)),
        subtitle_backend=str(request.get("subtitle_backend", "") or ""),
        engine_backend=str(request.get("engine_backend", "") or ""),
        edit_engine_backend=str(request.get("edit_engine_backend", "") or ""),
        highlight_engine_backend=str(request.get("highlight_engine_backend", "") or ""),
        progress_callback=progress_callback,
    )


def run_movie_story_request(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    """Run one of the current movie_story mainflows; old native/legacy are rejected."""

    if not output_script_path:
        output_script_path = str(request.get("output_script_path", "") or "")

    movie_story_mode = _resolve_movie_story_mode(request)
    if movie_story_mode in _ALLOWED_MOVIE_STORY_MODES:
        return run_movie_story_two_round_feature_mode(
            request=request,
            progress_callback=progress_callback,
            output_script_path=output_script_path,
            visual_enabled=movie_story_mode == "two_round_visual",
        )
    raise ValueError(f"unsupported_movie_story_mode:{movie_story_mode}")


def _resolve_movie_story_mode(request: Dict[str, Any]) -> str:
    """Resolve the explicit current movie_story mode without legacy fallback."""

    for key in ("movie_story_mode", "movie_story_feature_mode", "movie_story_strategy"):
        value = str(request.get(key) or "").strip().lower()
        if not value:
            continue
        return _validate_mainline_movie_story_mode(value)
    return "two_round"


def build_task_output_script_path(*, request: Dict[str, Any], task_dir: str) -> str:
    """Build the output path used by local job runner for movie_story script jobs."""

    requested = str(request.get("output_script_path", "") or "").strip()
    if requested:
        return requested
    return os.path.join(task_dir, "movie_story_script.json")
