from __future__ import annotations

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
from app.services.movie_story.engines import run_highlight_edit_engine, run_movie_story_engine

ProgressCallback = Optional[Callable[[int, str], None]]


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
        "movie_story_audit_clip_stages",
        "movie_story_audit_max_clips_per_stage",
        "boundary_merge_window_sec",
        "clip_match_tolerance_seconds",
        "scene_threshold",
        "min_scene_len",
    ]
    for key in passthrough_keys:
        if key in request and request.get(key) is not None:
            overrides[key] = request.get(key)
    return overrides


def run_unified_edit_request(
    *,
    entry: str,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    """Run a front-end edit request through one normalized movie-story entry layer."""

    mode_info = resolve_unified_mode(entry, request)
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
    mode_info = resolve_unified_mode(ENTRY_HIGHLIGHT_SCRIPT, request)
    prefer_raw_audio = bool(request.get("prefer_raw_audio", True)) or mode_info.mode == RAW_HIGHLIGHT
    return run_highlight_edit_engine(
        video_path=str(request.get("video_path", "") or ""),
        mode=engine_mode_for_highlight(mode_info.mode),
        target_duration_seconds=int(request.get("target_duration_seconds", 480) or 480),
        movie_title=str(request.get("movie_title", "") or ""),
        highlight_profile=str(request.get("highlight_profile", "auto") or "auto"),
        subtitle_path=str(request.get("subtitle_path", "") or ""),
        narration_text=str(request.get("narration_text", "") or ""),
        narration_audio_path=str(request.get("narration_audio_path", "") or ""),
        prefer_raw_audio=prefer_raw_audio,
        visual_mode=str(request.get("visual_mode", "auto") or "auto"),
        regenerate_subtitle=bool(request.get("regenerate_subtitle", False)),
        subtitle_backend=str(request.get("subtitle_backend", "") or ""),
        progress_callback=progress_callback,
    )


def run_movie_story_request(
    *,
    request: Dict[str, Any],
    progress_callback: ProgressCallback = None,
    output_script_path: str = "",
) -> Dict[str, Any]:
    regenerate_subtitle = str(request.get("cache_mode", "clear_and_regenerate") or "").strip() == "clear_and_regenerate"
    if not output_script_path:
        output_script_path = str(request.get("output_script_path", "") or "")

    return run_movie_story_engine(
        video_path=str(request.get("video_path", "") or ""),
        subtitle_path=str(request.get("subtitle_path", "") or ""),
        text_api_key=str(request.get("text_api_key", "") or ""),
        text_base_url=str(request.get("text_base_url", "") or ""),
        text_model=str(request.get("text_model", "") or ""),
        style=str(request.get("narration_style", "general") or "general"),
        generation_mode=str(request.get("generation_mode", "balanced") or "balanced"),
        visual_mode=str(request.get("visual_mode", "auto") or "auto"),
        output_script_path=output_script_path,
        scene_overrides=movie_story_scene_overrides_from_request(request),
        progress_callback=progress_callback,
        asr_backend=str(request.get("asr_backend", "") or ""),
        regenerate_subtitle=regenerate_subtitle,
    )


def build_task_output_script_path(*, request: Dict[str, Any], task_dir: str) -> str:
    requested = str(request.get("output_script_path", "") or "").strip()
    if requested:
        return requested
    return os.path.join(task_dir, "movie_story_script.json")
