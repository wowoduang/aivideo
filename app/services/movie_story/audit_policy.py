# -*- coding: utf-8 -*-
"""Audit export policy for the movie-story pipeline.

This module centralizes which intermediate stages are considered part of the
current production pipeline. It intentionally contains no business logic and no
LLM/video dependencies.
"""
from __future__ import annotations

import os
from typing import Iterable, Set

PRODUCTION_STAGES: Set[str] = {
    "00_active_movie_story_runtime",
    "00c_boundary_summary",
    "01_shot_candidates",
    "02_scene_candidates",
    "03_story_candidates",
    "04_global_story_context",
    "04a_llm_highlight_plan_before",
    "04a_llm_highlight_plan_after",
    "04a_llm_highlight_plan_error",
    "04b_apply_highlight_plan_before",
    "04b_apply_highlight_plan_after",
    "04b_apply_highlight_plan_error",
    "04c_select_final_story_evidence_before",
    "04c_select_final_story_evidence_after",
    "04c_select_final_story_evidence_error",
    "04d_collect_existing_scene_cut_points_before",
    "04d_collect_existing_scene_cut_points_after",
    "04d_collect_existing_scene_cut_points_error",
    "04e_extract_story_highlights_before",
    "04e_extract_story_highlights_after",
    "04e_extract_story_highlights_error",
    "04_typed_highlight_candidates",
    "05a_extract_highlight_frames_before",
    "05a_extract_highlight_frames_after",
    "05a_extract_highlight_frames_error",
    "05b_build_highlight_narration_evidence_before",
    "05b_build_highlight_narration_evidence_after",
    "05b_build_highlight_narration_evidence_error",
    "05b_highlight_planning_contract",
    "05_selected_highlights",
    "06_scene_evidence_for_narration",
    "06a_evidence_completeness",
    "06b_narration_generation_input_contract",
    "06c_understanding_quality_sample_contract",
    "06d_understanding_result_writeback_contract",
    "07a_generate_narration_before",
    "07a_generate_narration_after",
    "07a_generate_narration_error",
    "07_narration_generation_error",
    "07_narration_script_raw",
    "07_narration_script",
}

LEGACY_STAGES: Set[str] = {
    "01_plot_chunks",
    "02_scene_evidence",
    "04_story_highlights",
    "10_before_filter_script_items",
    "11_after_filter_script_items",
    "04a_scored_candidates",
    "04a_typed_highlight_candidates",
    "06_narration_script",
    "07_narration_script_legacy",
}

CLIP_EXPORT_STAGES: Set[str] = {
    "01_shot_candidates",
    "02_scene_candidates",
    "05_selected_highlights",
}

# These stages are mandatory for migration verification.  They must be kept
# even when a user's config still contains an older reduced
# movie_story_audit_keep_stages list from pre-migration builds.  They write
# JSON manifests only by default, so retaining them does not trigger expensive
# clip export.
MIGRATION_REQUIRED_STAGES: Set[str] = {
    "04_global_story_context",
    "05b_highlight_planning_contract",
    "06_scene_evidence_for_narration",
    "06a_evidence_completeness",
    "06b_narration_generation_input_contract",
    "06c_understanding_quality_sample_contract",
    "06d_understanding_result_writeback_contract",
}


def _split(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    return {x.strip() for x in str(raw).replace("；", ",").replace(";", ",").split(",") if x.strip()}


def _config_value(name: str, default: str = "") -> str:
    env = os.environ.get(name.upper())
    if env is not None:
        return env
    # Avoid hard dependency on the app config module. If it exists, read it.
    try:
        from app.config import config as app_config  # type: ignore
        app = getattr(app_config, "app", None)
        if isinstance(app, dict) and name in app:
            return str(app.get(name) or default)
        if app is not None and hasattr(app, name):
            return str(getattr(app, name) or default)
        if isinstance(app_config, dict):
            if name in app_config:
                return str(app_config.get(name) or default)
            nested = app_config.get("app")
            if isinstance(nested, dict) and name in nested:
                return str(nested.get(name) or default)
    except Exception as _e:
        logger.debug("配置字段读取失败，返回 default: {}", _e)
    return default


def _config_bool(name: str, default: bool = False) -> bool:
    raw = _config_value(name, "")
    if raw == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def include_legacy_stages() -> bool:
    """Opt in to legacy audit stages for migration/debug comparisons."""

    return _config_bool("movie_story_audit_include_legacy_stages", False)


def _include_legacy_effective(include_legacy: bool | None = None) -> bool:
    if include_legacy is not None:
        return bool(include_legacy)
    return include_legacy_stages()


def keep_stages(*, include_legacy: bool | None = None) -> Set[str]:
    configured = _split(_config_value("movie_story_audit_keep_stages", ""))
    # Always union mandatory migration stages with any user-configured keep list.
    # Without this, Stage-A can execute correctly while the audit output hides
    # 04/06, causing the verifier to fail with missing-stage errors.
    stages = (configured or set(PRODUCTION_STAGES)) | set(MIGRATION_REQUIRED_STAGES)
    if _include_legacy_effective(include_legacy):
        stages |= set(LEGACY_STAGES)
    return stages


def required_keep_stages() -> Set[str]:
    return set(MIGRATION_REQUIRED_STAGES)


def should_skip_stage(stage: str, *, include_legacy: bool | None = None) -> bool:
    name = str(stage or "")
    if name in LEGACY_STAGES and not _include_legacy_effective(include_legacy):
        return True
    keep = keep_stages(include_legacy=include_legacy)
    return bool(keep and name not in keep)


def should_export_clips(stage: str) -> bool:
    configured = _split(_config_value("movie_story_audit_clip_stages", ""))
    allowed = configured or set(CLIP_EXPORT_STAGES)
    return str(stage or "") in allowed


def production_stage_summary() -> dict:
    return {
        "production_stages": sorted(PRODUCTION_STAGES),
        "legacy_stages_skipped": sorted(LEGACY_STAGES),
        "legacy_stages_included": include_legacy_stages(),
        "clip_export_stages": sorted(CLIP_EXPORT_STAGES),
    }

# Full post-02 Movie Story closure stages are mandatory for diagnosing the real
# timeline runtime. They are manifest-only by default, so keeping them does not
# trigger expensive clip export.
FULL_CLOSURE_REQUIRED_STAGES = {
    "03_evidence_segments",
    "03_evidence_segments_error",
    "04_split_merge_suggestions",
    "06_rejected_candidates",
    "07_human_narration_director",
    "08_opening_hooks",
    "09_transition_sentences",
    "10_humanized_script_items",
    "11_subtitle_design_cues",
    "12_production_quality_gate",
    "13_movie_story_full_closure_summary",
}
PRODUCTION_STAGES.update(FULL_CLOSURE_REQUIRED_STAGES)
MIGRATION_REQUIRED_STAGES.update(FULL_CLOSURE_REQUIRED_STAGES)

# Diagnostic MP4 export stages for human judgement.
DIAGNOSTIC_VIDEO_EXPORT_STAGES = {
    "01a_shot_boundary_video_samples",
    "03a_evidence_video_samples",
    "04b_highlight_pre_selection_video_pool",
    "05a_selected_highlight_videos",
    "05b_selection_coverage_gate",
    "06b_rejected_near_miss_videos",
    "10a_script_review_videos",
}
PRODUCTION_STAGES.update(DIAGNOSTIC_VIDEO_EXPORT_STAGES)
MIGRATION_REQUIRED_STAGES.update(DIAGNOSTIC_VIDEO_EXPORT_STAGES)
CLIP_EXPORT_STAGES.update(DIAGNOSTIC_VIDEO_EXPORT_STAGES - {"05b_selection_coverage_gate"})

# Stage success gate audit stages. These are lightweight JSON/manifest stages
# used to decide whether the Movie Story flow can continue, not extra feature
# branches.
STAGE_SUCCESS_GATE_REQUIRED_STAGES = {
    "05b_selection_coverage_gate",
    "05c_coverage_fallback_selection",
}
try:
    PRODUCTION_STAGES.update(STAGE_SUCCESS_GATE_REQUIRED_STAGES)
except Exception as _e:
    logger.warning("PRODUCTION_STAGES.update 失败: {}", _e)
try:
    MIGRATION_REQUIRED_STAGES.update(STAGE_SUCCESS_GATE_REQUIRED_STAGES)
except Exception as _e:
    logger.warning("集合更新失败: {}", _e)

