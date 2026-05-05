from __future__ import annotations

"""Compatibility adapter for the retired subtitle-first pipeline.

The implementation has moved to ``app.services.movie_story.movie_story_native_engine``.
New code should call ``app.services.movie_story.unified_entry`` or
``app.services.movie_story.engines``.
"""

from app.services.movie_story.movie_story_native_engine import (
    _align_script_items_to_scene_cuts,
    _apply_full_subtitle_plan_to_chunks,
    _build_highlight_narration_segments,
    _build_highlight_only_script,
    _ensure_full_subtitle_highlight_windows,
    _extract_story_highlights,
    _filter_script_items_by_highlights,
    _resolve_prologue_end_from_strategy,
    _resolve_story_end_from_tail_markers,
    _select_final_story_evidence,
    _validate_pipeline_quality,
    run_movie_story_native_engine,
    run_native_movie_story_engine,
    run_subtitle_first_pipeline,
)

__all__ = [
    "run_movie_story_native_engine",
    "run_subtitle_first_pipeline",
    "run_native_movie_story_engine",
    "_resolve_prologue_end_from_strategy",
    "_resolve_story_end_from_tail_markers",
    "_align_script_items_to_scene_cuts",
    "_select_final_story_evidence",
    "_apply_full_subtitle_plan_to_chunks",
    "_filter_script_items_by_highlights",
    "_validate_pipeline_quality",
    "_extract_story_highlights",
    "_build_highlight_narration_segments",
    "_build_highlight_only_script",
    "_ensure_full_subtitle_highlight_windows",
]
