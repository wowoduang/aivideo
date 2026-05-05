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
    except Exception:
        pass
    return default


def keep_stages() -> Set[str]:
    configured = _split(_config_value("movie_story_audit_keep_stages", ""))
    # Always union mandatory migration stages with any user-configured keep list.
    # Without this, Stage-A can execute correctly while the audit output hides
    # 04/06, causing the verifier to fail with missing-stage errors.
    return (configured or set(PRODUCTION_STAGES)) | set(MIGRATION_REQUIRED_STAGES)


def required_keep_stages() -> Set[str]:
    return set(MIGRATION_REQUIRED_STAGES)


def should_skip_stage(stage: str) -> bool:
    name = str(stage or "")
    if name in LEGACY_STAGES:
        return True
    keep = keep_stages()
    return bool(keep and name not in keep)


def should_export_clips(stage: str) -> bool:
    configured = _split(_config_value("movie_story_audit_clip_stages", ""))
    allowed = configured or set(CLIP_EXPORT_STAGES)
    return str(stage or "") in allowed


def production_stage_summary() -> dict:
    return {
        "production_stages": sorted(PRODUCTION_STAGES),
        "legacy_stages_skipped": sorted(LEGACY_STAGES),
        "clip_export_stages": sorted(CLIP_EXPORT_STAGES),
    }
