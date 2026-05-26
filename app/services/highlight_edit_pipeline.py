from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.services.composition_plan_adapter import composition_plan_to_script_items
from app.services.highlight_selector import select_highlight_clips
from app.services.highlight_timeline_planner import plan_highlight_timeline
from app.services.movie_story import highlight_edit_candidates as movie_story_edit_candidates
from app.services.movie_story import highlight_edit_composition as movie_story_edit_composition
from app.services.movie_story import highlight_edit_context as movie_story_edit_context
from app.services.movie_story import highlight_edit_outputs as movie_story_edit_outputs
from app.services.movie_story import highlight_edit_selection as movie_story_edit_selection
from app.services.narrated_highlight_mapper import (
    fit_narration_units_to_target,
    map_narration_units_to_clips,
    split_narration_units,
)
from app.services.plot_chunker import build_plot_chunks_from_subtitles
from app.services.scene_builder import build_scenes, build_video_boundary_candidates
from app.services.subtitle_pipeline import build_subtitle_segments
from app.utils import utils


def run_highlight_edit_pipeline(
    video_path: str,
    *,
    mode: str = "highlight_recut",
    target_duration_seconds: int = 480,
    movie_title: str = "",
    highlight_profile: str = "auto",
    subtitle_path: str = "",
    narration_text: str = "",
    narration_audio_path: str = "",
    prefer_raw_audio: bool = True,
    visual_mode: str = "auto",
    regenerate_subtitle: bool = False,
    subtitle_backend: str = "",
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    def _progress(pct: int, msg: str = "") -> None:
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as _e:
                logger.warning("progress_callback 调用失败: {}", _e)

    try:
        return _run(
            video_path=video_path,
            mode=mode,
            target_duration_seconds=target_duration_seconds,
            movie_title=movie_title,
            highlight_profile=highlight_profile,
            subtitle_path=subtitle_path,
            narration_text=narration_text,
            narration_audio_path=narration_audio_path,
            prefer_raw_audio=prefer_raw_audio,
            visual_mode=visual_mode,
            regenerate_subtitle=regenerate_subtitle,
            subtitle_backend=subtitle_backend,
            progress=_progress,
        )
    except Exception as exc:
        logger.exception("粗剪编排主链执行失败: {}", exc)
        return movie_story_edit_outputs.build_error_response(str(exc))


def _run(
    *,
    video_path: str,
    mode: str,
    target_duration_seconds: int,
    movie_title: str,
    highlight_profile: str,
    subtitle_path: str,
    narration_text: str,
    narration_audio_path: str,
    prefer_raw_audio: bool,
    visual_mode: str,
    regenerate_subtitle: bool,
    subtitle_backend: str,
    progress: Callable[[int, str], None],
) -> Dict[str, Any]:
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    target_duration_seconds = max(int(target_duration_seconds or 0), 30)
    video_hash = utils.md5(video_path + str(os.path.getmtime(video_path)))
    visual_config = _resolve_visual_signal_config(visual_mode)

    progress(10, "准备字幕和分镜信号...")
    subtitle_result = build_subtitle_segments(
        video_path=video_path,
        explicit_subtitle_path=subtitle_path,
        regenerate=regenerate_subtitle,
        backend_override=subtitle_backend,
    )
    subtitle_segments = subtitle_result.get("segments") or []

    video_boundary_candidates: List[Dict[str, Any]] = []
    if visual_config["enabled"]:
        video_boundary_candidates = build_video_boundary_candidates(
            video_path=video_path,
            subtitle_segments=subtitle_segments,
            **visual_config["boundary_args"],
        )
    scene_segments = build_scenes(
        subtitle_segments=subtitle_segments,
        video_path=video_path if visual_config["enabled"] else "",
        mode=visual_config["mode"],
        preset=visual_config["scene_preset"],
    )

    progress(30, "构建候选片段...")
    plot_chunks: List[Dict[str, Any]] = []
    if subtitle_segments:
        plot_chunks = build_plot_chunks_from_subtitles(
            subtitle_segments,
            target_duration_minutes=max(round(target_duration_seconds / 60), 1),
            video_candidates=video_boundary_candidates,
            refine_chunks=True,
        )

    plot_candidate_clips = _build_candidate_clips(
        plot_chunks=plot_chunks,
        scene_segments=scene_segments,
        subtitle_segments=subtitle_segments,
    )
    scene_candidate_clips = _build_scene_candidates(
        scene_segments=scene_segments,
        plot_chunks=plot_chunks,
        video_boundary_candidates=video_boundary_candidates,
        subtitle_segments=subtitle_segments,
    )

    shared_audio_context = movie_story_edit_context.build_shared_audio_signal_context(video_path)
    plot_candidate_clips, plot_audio_stats = _annotate_audio_signal_context(
        video_path,
        plot_candidate_clips,
        audio_context=shared_audio_context,
    )
    scene_candidate_clips, scene_audio_stats = _annotate_audio_signal_context(
        video_path,
        scene_candidate_clips,
        audio_context=shared_audio_context,
    )

    raw_candidate_clips = _merge_unique_clips(plot_candidate_clips, scene_candidate_clips)
    highlight_capabilities = _detect_highlight_capabilities()
    highlight_profile_context = _resolve_highlight_profile_context(
        requested_profile=highlight_profile,
        movie_title=movie_title,
        narration_text=narration_text,
        subtitle_segments=subtitle_segments,
        plot_chunks=plot_chunks,
        candidate_clips=raw_candidate_clips,
        capabilities=highlight_capabilities,
    )
    plot_candidate_clips = _apply_highlight_profile_context(plot_candidate_clips, highlight_profile_context)
    scene_candidate_clips = _apply_highlight_profile_context(scene_candidate_clips, highlight_profile_context)
    candidate_clips = _merge_unique_clips(plot_candidate_clips, scene_candidate_clips)
    candidate_stats = _build_candidate_stats(
        subtitle_segments=subtitle_segments,
        plot_chunks=plot_chunks,
        scene_segments=scene_segments,
        plot_candidate_clips=plot_candidate_clips,
        scene_candidate_clips=scene_candidate_clips,
        merged_candidate_clips=candidate_clips,
        visual_mode=visual_config["mode"],
        highlight_profile=highlight_profile_context,
        capabilities=highlight_capabilities,
        plot_audio_stats=plot_audio_stats,
        scene_audio_stats=scene_audio_stats,
    )

    ai_highlight_selection = _try_ai_highlight_selection(
        candidate_clips,
        target_duration_seconds=target_duration_seconds,
        movie_title=movie_title,
        mode=mode,
        highlight_profile=highlight_profile_context,
    )
    candidate_stats["ai_highlight_selection_used"] = bool(ai_highlight_selection.get("used_ai"))
    candidate_stats["ai_highlight_selected_count"] = len(ai_highlight_selection.get("selected_clip_ids") or [])
    candidate_stats["ai_highlight_model"] = str(ai_highlight_selection.get("model", "") or "")

    narration_units: List[Dict[str, Any]] = []
    narration_matches: List[Dict[str, Any]] = []
    selection_top_k = max(round(target_duration_seconds / 35), 4)

    if mode == "narrated_highlight_edit" and str(narration_text or "").strip():
        progress(48, "分析解说结构...")
        narration_units = fit_narration_units_to_target(
            split_narration_units(narration_text, 0),
            target_duration_seconds,
        )
        progress(60, "按解说构建粗匹配候选...")
        narrated_pool = _build_narrated_clip_pool(
            plot_candidate_clips,
            scene_candidate_clips,
            narration_units,
            target_duration_seconds,
        )
        progress(72, "匹配解说和场景...")
        narration_matches = _try_ai_narration_matching(
            narration_units,
            narrated_pool,
            movie_title=movie_title,
            highlight_profile=highlight_profile_context,
        )
        candidate_stats["ai_narration_matching_used"] = bool(narration_matches)
        if not narration_matches:
            narration_matches = map_narration_units_to_clips(narration_units, narrated_pool)
        selected_clips = _merge_unique_clips(
            _collect_matched_clips(narration_matches),
            _select_clips_by_ids(
                candidate_clips,
                ai_highlight_selection.get("selected_clip_ids") or [],
                raw_audio_clip_ids=ai_highlight_selection.get("raw_audio_clip_ids") or [],
            ),
            select_highlight_clips(candidate_clips, top_k=max(selection_top_k, len(narration_units))),
        )
        if not selected_clips:
            selected_clips = select_highlight_clips(
                candidate_clips,
                top_k=max(selection_top_k, len(narration_units), 4),
            )
        progress(80, "规划时间轴...")
        planned_clips = plan_highlight_timeline(selected_clips, target_duration_seconds)
        if any(bool(item.get("preserve_sentence_boundary")) for item in narration_matches):
            narration_matches = _refresh_narration_matches_from_planned(narration_matches, planned_clips or selected_clips)
        else:
            narration_matches = map_narration_units_to_clips(narration_units, planned_clips or selected_clips)
    else:
        progress(55, "筛选高光片段...")
        selected_clips = _select_clips_by_ids(
            candidate_clips,
            ai_highlight_selection.get("selected_clip_ids") or [],
            raw_audio_clip_ids=ai_highlight_selection.get("raw_audio_clip_ids") or [],
        )
        if _selection_duration(selected_clips) < max(min(target_duration_seconds * 0.4, 90.0), 24.0):
            selected_clips = _merge_unique_clips(
                selected_clips,
                _build_highlight_recut_selection_pool(
                    candidate_clips,
                    target_duration_seconds=target_duration_seconds,
                    subtitle_segments=subtitle_segments,
                    plot_chunks=plot_chunks,
                    highlight_profile=highlight_profile_context,
                ),
            )
        if not selected_clips:
            selected_clips = _build_highlight_recut_selection_pool(
                candidate_clips,
                target_duration_seconds=target_duration_seconds,
                subtitle_segments=subtitle_segments,
                plot_chunks=plot_chunks,
                highlight_profile=highlight_profile_context,
            )
        if not selected_clips:
            selected_clips = select_highlight_clips(
                candidate_clips,
                top_k=selection_top_k,
            )
        progress(72, "规划时间轴...")
        planned_clips = plan_highlight_timeline(selected_clips, target_duration_seconds)

    progress(88, "生成粗剪合成脚本...")
    composition_plan = _build_composition_plan(
        mode=mode,
        video_path=video_path,
        movie_title=movie_title,
        target_duration_seconds=target_duration_seconds,
        visual_mode=visual_config["mode"],
        highlight_profile=highlight_profile_context,
        highlight_capabilities=highlight_capabilities,
        candidate_stats=candidate_stats,
        selected_clips=planned_clips,
        narration_text=narration_text,
        narration_audio_path=narration_audio_path,
        prefer_raw_audio=prefer_raw_audio,
        narration_matches=narration_matches,
    )
    script_items = composition_plan_to_script_items(composition_plan)

    progress(96, "保存粗剪脚本...")
    output_paths = _write_outputs(video_hash, composition_plan, script_items)

    progress(100, "粗剪编排主链完成")
    return movie_story_edit_outputs.build_success_response(
        mode=mode,
        subtitle_result=subtitle_result,
        subtitle_segments=subtitle_segments,
        scene_segments=scene_segments,
        video_boundary_candidates=video_boundary_candidates,
        plot_chunks=plot_chunks,
        plot_candidate_clips=plot_candidate_clips,
        candidate_clips=candidate_clips,
        scene_candidate_clips=scene_candidate_clips,
        candidate_stats=candidate_stats,
        highlight_profile=highlight_profile_context,
        highlight_capabilities=highlight_capabilities,
        selected_clips=planned_clips,
        narration_units=narration_units,
        narration_matches=narration_matches,
        composition_plan=composition_plan,
        output_paths=output_paths,
        script_items=script_items,
    )


# Stage-K compatibility aliases.  The implementation now lives in
# app.services.movie_story.highlight_edit_candidates and
# app.services.movie_story.highlight_edit_composition.  Keep these names so
# older tests/imports continue to work while the pipeline becomes a thin
# orchestrator.
_build_candidate_clips = movie_story_edit_candidates.build_candidate_clips
_build_scene_candidates = movie_story_edit_candidates.build_scene_candidates
_build_candidate_stats = movie_story_edit_candidates.build_candidate_stats
_build_narrated_clip_pool = movie_story_edit_candidates.build_narrated_clip_pool
_collect_matched_clips = movie_story_edit_candidates.collect_matched_clips
_build_scene_candidate = movie_story_edit_candidates.build_scene_candidate
_build_subtitle_segment_map = movie_story_edit_candidates.build_subtitle_segment_map
_collect_scene_dialogue_signals = movie_story_edit_candidates.collect_scene_dialogue_signals
_build_composition_plan = movie_story_edit_composition.build_composition_plan
_plan_group_shot_durations = movie_story_edit_composition.plan_group_shot_durations
_decide_group_audio_plan = movie_story_edit_composition.decide_group_audio_plan
_split_narration_text_for_group = movie_story_edit_composition.split_narration_text_for_group
_build_intra_scene_subshots = movie_story_edit_composition.build_intra_scene_subshots
_expand_group_with_intra_scene_subshots = movie_story_edit_composition.expand_group_with_intra_scene_subshots

# Stage-L compatibility aliases.  Runtime context and output helpers now live in
# app.services.movie_story.highlight_edit_context and highlight_edit_outputs.
_resolve_visual_signal_config = movie_story_edit_context.resolve_visual_signal_config
_try_ai_highlight_selection = movie_story_edit_context.try_ai_highlight_selection
_try_ai_narration_matching = movie_story_edit_context.try_ai_narration_matching
_select_clips_by_ids = movie_story_edit_context.select_clips_by_ids
_refresh_narration_matches_from_planned = movie_story_edit_context.refresh_narration_matches_from_planned
_selection_duration = movie_story_edit_context.selection_duration
_detect_highlight_capabilities = movie_story_edit_context.detect_highlight_capabilities
_resolve_highlight_profile_context = movie_story_edit_context.resolve_highlight_profile_context
_apply_highlight_profile_context = movie_story_edit_context.apply_highlight_profile_context
_annotate_audio_signal_context = movie_story_edit_context.annotate_audio_signal_context
_write_outputs = movie_story_edit_outputs.write_outputs


def _clip_overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    return movie_story_edit_selection.clip_overlap_ratio(left, right)


def _sorted_unique_values(values: List[Any]) -> List[Any]:
    return movie_story_edit_selection.sorted_unique_values(values)


def _ordered_unique_values(values: List[Any]) -> List[Any]:
    return movie_story_edit_selection.ordered_unique_values(values)


def _detect_main_character_reference(candidate_clips: List[Dict[str, Any]]) -> List[str]:
    return movie_story_edit_selection.detect_main_character_reference(candidate_clips)


def _build_highlight_recut_selection_pool(
    candidate_clips: List[Dict[str, Any]],
    target_duration_seconds: int,
    *,
    subtitle_segments: Optional[List[Dict[str, Any]]] = None,
    plot_chunks: Optional[List[Dict[str, Any]]] = None,
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    return movie_story_edit_selection.build_highlight_recut_selection_pool(
        candidate_clips,
        target_duration_seconds,
        subtitle_segments=subtitle_segments,
        plot_chunks=plot_chunks,
        highlight_profile=highlight_profile,
        select_highlight_fn=select_highlight_clips,
    )


def _merge_unique_clips(*clip_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return movie_story_edit_selection.merge_unique_clips(*clip_groups)


def _build_coverage_clips(candidate_clips: List[Dict[str, Any]], desired_count: int) -> List[Dict[str, Any]]:
    # Kept as a compatibility shim for older tests/imports.  Coverage anchors
    # are now built inside movie_story.highlight_edit_selection.
    pool = movie_story_edit_selection.build_highlight_recut_selection_pool(
        candidate_clips,
        max(int(desired_count or 1) * 35, 35),
        select_highlight_fn=select_highlight_clips,
    )
    return [clip for clip in pool if "coverage_anchor" in set(clip.get("selection_reason") or [])][: max(int(desired_count or 0), 1)]
