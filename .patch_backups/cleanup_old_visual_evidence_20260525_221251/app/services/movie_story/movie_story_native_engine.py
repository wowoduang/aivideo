from __future__ import annotations

"""Native movie-story narration engine.

The movie-story implementation lives here as the native backend. The old subtitle_first_pipeline module is now only a compatibility adapter.
The old public module is now a compatibility adapter.
"""

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.services.evidence_fuser import fuse_scene_evidence
try:
    from app.services.movie_story.story_runtime import (
        build_authoritative_plot_chunks,
        extract_highlights as select_typed_story_highlights,
        keep_scene_evidence as keep_authoritative_scene_evidence,
        normalize_script_items_without_retiming,
        refresh_authoritative_plot_map,
    )
except ImportError:  # compatibility with lightweight unit-test stubs
    from app.services.movie_story.story_runtime import (
        build_authoritative_plot_chunks,
        extract_highlights as select_typed_story_highlights,
        keep_scene_evidence as keep_authoritative_scene_evidence,
        normalize_script_items_without_retiming,
    )

    def refresh_authoritative_plot_map(items, stage: str = "plot_chunks_refreshed"):
        return items
from app.services.scene_builder import build_video_boundary_candidates, detect_scenes_from_video
from app.services.plot_understanding_clean import (
    add_local_understanding,
    build_full_subtitle_understanding,
    build_global_summary,
    plan_story_highlights,
)
from app.services.preflight_check import PreflightError, validate_script_items
from app.services.representative_frames import extract_representative_frames_for_scenes
from app.services.script_fallback import ensure_script_shape
try:
    from app.services.llm_config import get_text_llm_config
except Exception:  # lightweight unit-test stubs may not initialize full config/logger
    def get_text_llm_config() -> Dict[str, str]:
        return {"api_key": "", "base_url": "", "model": ""}

try:
    from app.services.llm_text_completion import call_text_chat_completion
except Exception:  # lightweight unit-test stubs may not initialize full config/logger
    def call_text_chat_completion(*args, **kwargs):
        return ""
from app.services.story_boundary_aligner import align_story_boundaries, collect_candidate_boundaries
from app.services.story_validator_clean import validate_story_segments
from app.services.subtitle_pipeline import build_subtitle_segments
from app.services.movie_story.evidence_enrichment import (
    build_global_story_context,
    enrich_evidence_items,
    evaluate_evidence_items,
)
from app.services.movie_story.story_window import (
    _apply_full_subtitle_plan_to_chunks,
    _apply_llm_highlight_plan,
    _build_prompt_highlight_windows_from_story_highlights,
    _clip_highlight_ranges_to_story_window,
    _clip_range_after_prologue,
    _clip_range_before_story_end,
    _collect_highlight_ranges,
    _dedupe_prompt_highlight_windows,
    _detect_tail_markers,
    _ensure_full_subtitle_highlight_windows,
    _highlight_plan_windows,
    _infer_first_speech_time,
    _is_meaningful_speech_segment,
    _normalize_prompt_highlight_window,
    _normalize_tail_text,
    _parse_prompt_time,
    _ranges_overlap,
    _resolve_highlight_category,
    _resolve_prologue_end_from_strategy,
    _resolve_story_end_from_tail_markers,
    _score_tail_credits_marker,
    _score_tail_preview_marker,
)
from app.services.movie_story.narration_evidence import (
    _build_highlight_local_understanding,
    _build_highlight_narration_segments,
    _build_highlight_only_script,
    _build_highlight_story_validation,
    _build_highlight_visual_summary,
    _collect_highlight_source_packages,
    _highlight_frame_budget,
    _merge_text_snippets,
    _prepare_highlight_frame_targets,
    _representative_frame_desc,
    _select_narration_evidence_for_generation,
    _unique_strings,
)
from app.services.movie_story.narration_runtime import (
    _build_disabled_migration_script_items,
    _generate_narration_with_mode,
)
from app.services.movie_story.narration_finalize import (
    align_script_items_to_scene_cuts as _align_script_items_to_scene_cuts,
    filter_script_items_by_highlights as _filter_script_items_by_highlights,
    finalize_narration_script,
    lock_narration_items_to_semantic_windows as _lock_narration_items_to_semantic_windows,
)
from app.services.segment_visual_understanding import (
    enrich_scene_evidence_with_visual_cards,
    refine_script_items_with_visual_cards,
    write_visual_audit_files,
)

from app.services.movie_story.audit_runtime import (
    _audit_config_value_v41,
    _audit_bool_v41,
    _audit_int_v41,
    _audit_video_snapshot,
    _audit_pipeline_marker,
)
from app.services.movie_story.runtime_options import (
    _resolve_target_minutes,
    _resolve_visual_mode,
    _looks_like_placeholder_secret,
    _has_real_llm_config,
    _ensure_llm_ready,
    _runtime_config_value,
    _runtime_bool,
    _runtime_int,
    _movie_story_migration_stage,
    _resolve_narration_llm_mode,
    _stage_llm_enabled,
    _run_traced_stage,
)
from app.services.movie_story.time_utils import normalize_time_fields_in_items
from app.services.movie_story.scene_alignment import (
    _collect_scene_cut_points,
    _collect_scene_cut_points_from_existing,
    _align_range_to_scene_group,
    _semantic_window_for_script_item,
)
from app.services.movie_story.highlight_runtime import (
    _safe_plan_story_highlights,
    _fallback_global_summary,
    _build_story_candidates_from_evidence,
    _extract_story_highlights,
    _resolve_highlight_selectivity,
    _select_final_story_evidence,
)
from app.services.movie_story.quality_gate import (
    _validate_pipeline_quality,
    _build_story_audit_payload,
)
from app.services.movie_story.composition_bridge import (
    build_movie_story_composition_plan,
    validate_composition_plan,
)
from app.services.movie_story.direct_cut_runtime import (
    force_direct_cut_script_contract as _force_direct_cut_script_contract,
    is_direct_cut_first_item as _is_direct_cut_first_item,
    is_direct_cut_style as _is_direct_cut_style,
    run_direct_cut_after_subtitles as _run_direct_cut_after_subtitles,
)
from app.services.movie_story.legacy_understanding_adapter import (
    build_legacy_full_subtitle_understanding,
    build_understanding_script_payload,
    build_understanding_baseline_report,
    run_legacy_understanding_chain,
    select_story_highlights_with_legacy_priority,
    write_understanding_script,
    write_understanding_baseline_report,
)
from app.services.movie_story.legacy_segment_understanding import enrich_legacy_segment_understanding
from app.utils import utils



_SCENE_ALIGN_NARRATION_WINDOW_SECONDS = 1.2
_SCENE_ALIGN_RAW_VOICE_WINDOW_SECONDS = 4.0
_HIGHLIGHT_SNAP_WINDOW_DEFAULT_SECONDS = 1.5
_HIGHLIGHT_SNAP_WINDOW_HIGH_SECONDS = 2.5
_HIGHLIGHT_SNAP_WINDOW_RAW_VOICE_SECONDS = 4.0

MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING = "legacy_understanding"
MOVIE_STORY_STRATEGY_NATIVE_RUNTIME = "native_runtime"
_BLOCKING_UNDERSTANDING_QUALITY_ISSUES = {
    "scene_evidence_missing",
    "segment_local_understanding_missing",
    "story_validation_missing",
}


def _resolve_movie_story_strategy(scene_overrides: Dict[str, Any]) -> str:
    raw = str(
        scene_overrides.get("movie_story_strategy")
        or scene_overrides.get("understanding_strategy")
        or scene_overrides.get("chain_strategy")
        or ""
    ).strip().lower().replace("-", "_")
    aliases = {
        "legacy": MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING,
        "old": MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING,
        "old_understanding": MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING,
        "subtitle_first": MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING,
        "deep_understanding": MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING,
        "native": MOVIE_STORY_STRATEGY_NATIVE_RUNTIME,
        "new": MOVIE_STORY_STRATEGY_NATIVE_RUNTIME,
        "typed": MOVIE_STORY_STRATEGY_NATIVE_RUNTIME,
        "runtime": MOVIE_STORY_STRATEGY_NATIVE_RUNTIME,
    }
    normalized = aliases.get(raw, raw)
    if normalized in {MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING, MOVIE_STORY_STRATEGY_NATIVE_RUNTIME}:
        return normalized
    return MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING


def _apply_llm_highlight_plan_nonblocking(
    scene_evidence: List[Dict[str, Any]],
    full_subtitle_understanding: Dict[str, Any],
    llm_highlight_plan: Dict[str, Any],
    audit_vars: Dict[str, Any],
) -> List[Dict[str, Any]]:
    try:
        return _apply_llm_highlight_plan(scene_evidence, full_subtitle_understanding, llm_highlight_plan)
    except Exception as exc:
        logger.exception("高光计划应用失败，已跳过 04b 并继续主链: {}", exc)
        try:
            _audit_pipeline_marker(
                "04b_apply_highlight_plan_skipped",
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "scene_evidence_count": len(scene_evidence or []),
                    "plan_policy": (llm_highlight_plan or {}).get("plan_policy"),
                    "fallback": "use_unannotated_scene_evidence",
                },
                audit_vars,
            )
        except Exception as audit_exc:
            logger.warning("04b_apply_highlight_plan_skipped 审计写入失败: {}", audit_exc)

        fallback: List[Dict[str, Any]] = []
        for item in scene_evidence or []:
            if not isinstance(item, dict):
                continue
            cur = dict(item)
            cur.setdefault("llm_highlight_selected", bool(cur.get("llm_window_selected")))
            cur.setdefault("llm_highlight_rejected", False)
            cur.setdefault("llm_highlight_reason", "")
            cur.setdefault("llm_window_reasons", list(cur.get("llm_window_reasons") or []))
            cur.setdefault("llm_window_categories", list(cur.get("llm_window_categories") or []))
            cur["llm_highlight_plan_skipped"] = True
            cur["llm_highlight_plan_error"] = str(exc)
            fallback.append(cur)
        return fallback



def run_movie_story_native_engine(
    video_path: str,
    subtitle_path: str = "",
    *,
    text_api_key: str = "",
    text_base_url: str = "",
    text_model: str = "",
    style: str = "general",
    keyframe_dir: str = "",
    output_script_path: str = "",
    generation_mode: str = "balanced",
    visual_mode: str = "",
    scene_overrides: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    asr_backend: str = "",
    regenerate_subtitle: bool = False,
) -> Dict[str, Any]:
    def _progress(pct: int, msg: str = "") -> None:
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as _e:
                logger.warning("progress_callback 调用异常: {}", _e)

    try:
        return _run(
            video_path=video_path,
            subtitle_path=subtitle_path,
            text_api_key=text_api_key,
            text_base_url=text_base_url,
            text_model=text_model,
            style=style,
            output_script_path=output_script_path,
            generation_mode=generation_mode,
            visual_mode=visual_mode,
            scene_overrides=scene_overrides or {},
            progress=_progress,
            asr_backend=asr_backend,
            regenerate_subtitle=regenerate_subtitle,
        )
    except Exception as exc:
        logger.exception("影视解说主链执行失败: {}", exc)
        return {
            "script_items": [],
            "script_path": "",
            "success": False,
            "error": str(exc),
        }
















































































































































































































































def _run(
    video_path: str,
    subtitle_path: str,
    text_api_key: str,
    text_base_url: str,
    text_model: str,
    style: str,
    output_script_path: str,
    generation_mode: str,
    visual_mode: str,
    scene_overrides: Dict[str, Any],
    progress: Callable[[int, str], None],
    asr_backend: str,
    regenerate_subtitle: bool,
) -> Dict[str, Any]:
    # 确保 LLM 配置就绪（从参数或配置读取）；配置缺失时不再中断流程，而是进入 fallback 闭环。
    skip_llm = str(scene_overrides.get("skip_llm", "")).strip().lower() in {"1", "true", "yes", "on"}
    if skip_llm:
        text_api_key, text_base_url, text_model = "", "", ""
        visual_mode = "off"
        scene_overrides = dict(scene_overrides)
        scene_overrides.update({
            "movie_story_narration_llm_mode": "disabled",
            "movie_story_enable_full_subtitle_llm": False,
            "movie_story_enable_global_llm": False,
            "movie_story_enable_segment_llm": False,
            "movie_story_enable_story_validation_llm": False,
            "movie_story_enable_highlight_plan_llm": False,
            "movie_story_disable_llm_highlight_plan": True,
        })
    else:
        text_api_key, text_base_url, text_model = _ensure_llm_ready(text_api_key, text_base_url, text_model)
    has_llm = _has_real_llm_config(text_api_key, text_model)
    asr_backend = str(asr_backend or "faster-whisper").strip() or "faster-whisper"
    target_minutes = _resolve_target_minutes(generation_mode, scene_overrides)
    effective_visual_mode = _resolve_visual_mode(visual_mode or scene_overrides.get("visual_mode", "auto"))
    highlight_only = bool(scene_overrides.get("highlight_only", False))
    highlight_selectivity = _resolve_highlight_selectivity(scene_overrides.get("highlight_selectivity", "balanced"))
    narrative_strategy = str(scene_overrides.get("narrative_strategy") or "chronological")
    accuracy_priority = str(scene_overrides.get("accuracy_priority") or "high")
    video_title = str(scene_overrides.get("video_title") or scene_overrides.get("short_name") or "").strip()
    movie_story_strategy = _resolve_movie_story_strategy(scene_overrides)
    use_legacy_understanding = movie_story_strategy == MOVIE_STORY_STRATEGY_LEGACY_UNDERSTANDING
    direct_cut_requested = _is_direct_cut_style(style)

    migration_stage = _movie_story_migration_stage(scene_overrides)
    narration_llm_mode = _resolve_narration_llm_mode(scene_overrides, has_llm)
    narration_llm_max_segments = int(scene_overrides.get("movie_story_narration_llm_max_segments") or scene_overrides.get("narration_llm_max_segments") or _runtime_int("movie_story_narration_llm_max_segments", "AIVIDEO_MOVIE_STORY_NARRATION_LLM_MAX_SEGMENTS", 12))
    # Old full_subtitle_understanding_v2 is not part of the active
    # movie_story mainflow. Keep it explicit-only through config/env.
    enable_full_subtitle_llm = _stage_llm_enabled(scene_overrides, "movie_story_enable_full_subtitle_llm", "AIVIDEO_MOVIE_STORY_ENABLE_FULL_SUBTITLE_LLM", False, has_llm)
    # Old global story LLM is not part of the active movie_story mainflow.
    # Keep it explicit-only through config/env.
    enable_global_llm = _stage_llm_enabled(scene_overrides, "movie_story_enable_global_llm", "AIVIDEO_MOVIE_STORY_ENABLE_GLOBAL_LLM", False, has_llm)
    enable_segment_llm = _stage_llm_enabled(scene_overrides, "movie_story_enable_segment_llm", "AIVIDEO_MOVIE_STORY_ENABLE_SEGMENT_LLM", has_llm if use_legacy_understanding else False, has_llm)
    enable_story_validation_llm = _stage_llm_enabled(scene_overrides, "movie_story_enable_story_validation_llm", "AIVIDEO_MOVIE_STORY_ENABLE_STORY_VALIDATION_LLM", has_llm if use_legacy_understanding else False, has_llm)
    enable_highlight_plan_llm = _stage_llm_enabled(scene_overrides, "movie_story_enable_highlight_plan_llm", "AIVIDEO_MOVIE_STORY_ENABLE_HIGHLIGHT_PLAN_LLM", False, has_llm)
    if direct_cut_requested:
        effective_visual_mode = "off"
        narration_llm_mode = "disabled"
        enable_full_subtitle_llm = False
        enable_global_llm = False
        enable_segment_llm = False
        enable_story_validation_llm = False
        enable_highlight_plan_llm = False
    if skip_llm:
        logger.warning("movie_story skip_llm=true: text LLM and visual LLM stages are disabled for flow testing.")
    logger.info(
        "影视解说 LLM 模式: has_llm={}, narration_mode={}, full_subtitle_llm={}, global_llm={}, segment_llm={}, validation_llm={}, highlight_plan_llm={}",
        has_llm, narration_llm_mode, enable_full_subtitle_llm, enable_global_llm, enable_segment_llm, enable_story_validation_llm, enable_highlight_plan_llm,
    )

    progress(10, "字幕解析与标准化...")
    
    # 启动一个后台线程来模拟字幕识别进度（因为 build_subtitle_segments 没有进度回调）
    import threading
    import time
    
    stop_progress_simulator = threading.Event()
    def simulate_subtitle_progress():
        """模拟字幕识别进度，从 10% 到 16%"""
        for i in range(11, 17):  # 11% 到 16%
            if stop_progress_simulator.wait(2):  # 每 2 秒更新一次
                break
            progress(i, f"字幕识别中... ({i}%)")
    
    # 启动进度模拟线程
    progress_thread = threading.Thread(target=simulate_subtitle_progress)
    progress_thread.start()
    
    try:
        sub_result = build_subtitle_segments(
            video_path=video_path,
            explicit_subtitle_path=subtitle_path,
            regenerate=regenerate_subtitle,
            backend_override=asr_backend,
        )
    finally:
        # 停止进度模拟
        stop_progress_simulator.set()
        progress_thread.join(timeout=1)
    
    segments = normalize_time_fields_in_items(sub_result.get("segments") or [])
    if not segments:
        raise ValueError(f"无法获取有效字幕 (source={sub_result.get('source')}, error={sub_result.get('error', '')})")

    logger.info(
        "影视解说 M1 完成: source={}, backend={}, regenerate={}, segments={}, subtitle_path={}",
        sub_result.get("source"),
        sub_result.get("backend"),
        sub_result.get("regenerate"),
        len(segments),
        sub_result.get("subtitle_path", ""),
    )

    if direct_cut_requested:
        return _run_direct_cut_after_subtitles(
            video_path=video_path,
            output_script_path=output_script_path,
            style=style,
            video_title=video_title,
            generation_mode=generation_mode,
            target_minutes=target_minutes,
            movie_story_strategy=movie_story_strategy,
            migration_stage=migration_stage,
            highlight_only=highlight_only,
            scene_overrides=scene_overrides,
            sub_result=sub_result,
            segments=segments,
            progress=progress,
            api_key=text_api_key,
            base_url=text_base_url,
            model=text_model,
        )

    progress(18, "整字幕剧情理解与高光规划...")
    if use_legacy_understanding:
        full_subtitle_understanding, prologue_warnings, tail_warnings = build_legacy_full_subtitle_understanding(
            subtitle_segments=segments,
            api_key=text_api_key,
            base_url=text_base_url,
            model=text_model,
            scene_overrides=scene_overrides,
            resolve_prologue=_resolve_prologue_end_from_strategy,
            resolve_tail=_resolve_story_end_from_tail_markers,
        )
    else:
        full_subtitle_understanding = build_full_subtitle_understanding(
            segments,
            api_key=text_api_key if enable_full_subtitle_llm else "",
            base_url=text_base_url if enable_full_subtitle_llm else "",
            model=text_model if enable_full_subtitle_llm else "",
        )
        full_subtitle_understanding, prologue_warnings = _resolve_prologue_end_from_strategy(
            full_subtitle_understanding=full_subtitle_understanding,
            subtitle_segments=segments,
            scene_overrides=scene_overrides,
        )
        full_subtitle_understanding, tail_warnings = _resolve_story_end_from_tail_markers(
            full_subtitle_understanding=full_subtitle_understanding,
            subtitle_segments=segments,
        )

    progress(22, "检测视频候选边界...")
    video_boundary_candidates: List[Dict[str, Any]] = []
    if effective_visual_mode != "off":
        video_boundary_candidates = build_video_boundary_candidates(
            video_path=video_path,
            subtitle_segments=segments,
            threshold=float(scene_overrides.get("scene_threshold", 27.0) or 27.0),
            min_scene_len=float(scene_overrides.get("min_scene_len", 2.0) or 2.0),
            merge_window_sec=float(scene_overrides.get("boundary_merge_window_sec", 2.0) or 2.0),
        )

    progress(28, "字幕粗分段与剧情块规划...")
    plot_chunks = build_authoritative_plot_chunks(
        segments,
        target_duration_minutes=target_minutes,
        narrative_strategy=narrative_strategy,
        accuracy_priority=accuracy_priority,
        highlight_selectivity=highlight_selectivity,
        video_candidates=video_boundary_candidates,
        refine_chunks=True,
        video_path=video_path,
        output_script_path=output_script_path,
        visual_mode=effective_visual_mode,
        movie_story_strategy=movie_story_strategy,
    )
    if not plot_chunks:
        raise ValueError("剧情块规划失败，未生成任何剧情块")
    plot_chunks = normalize_time_fields_in_items(plot_chunks)
    _audit_video_snapshot("01_plot_chunks", plot_chunks, locals())
    logger.info("影视解说 M2 完成: {} 个剧情块", len(plot_chunks))

    progress(36, "整剧理解...")
    if enable_global_llm:
        global_summary = build_global_summary(
            plot_chunks,
            api_key=text_api_key,
            base_url=text_base_url,
            model=text_model,
        )
    else:
        global_summary = _fallback_global_summary(plot_chunks, full_subtitle_understanding, video_title=video_title)
    global_summary.update(
        {
            "target_duration_minutes": target_minutes,
            "narrative_strategy": narrative_strategy,
            "accuracy_priority": accuracy_priority,
            "video_title": video_title,
            "full_subtitle_understanding": full_subtitle_understanding,
        }
    )
    # Stage-A migration gate: normalize global context before any local evidence is built.
    global_summary = build_global_story_context(
        plot_chunks=plot_chunks,
        full_subtitle_understanding=full_subtitle_understanding,
        existing_global_summary=global_summary,
        video_title=video_title,
    )
    _audit_video_snapshot("04_global_story_context", [{
        "candidate_id": "global_story_context",
        "candidate_type": "global_story_context",
        "start": 0.0,
        "end": 0.001,
        "duration": 0.001,
        "timestamp": "00:00:00,000-00:00:00,001",
        "text": json.dumps(global_summary, ensure_ascii=False)[:1200],
        "main_conflict": global_summary.get("main_conflict"),
        "story_theme": global_summary.get("story_theme"),
        "genre": global_summary.get("genre"),
        "main_characters": global_summary.get("main_characters"),
        "timeline_summary": global_summary.get("timeline_summary"),
        "migration_quality": global_summary.get("migration_quality"),
    }], locals())

    progress(46, "剧情边界吸附...")
    subtitle_boundaries = collect_candidate_boundaries(segments)
    candidate_boundaries = list(subtitle_boundaries) + list(video_boundary_candidates)
    plot_chunks = align_story_boundaries(
        plot_chunks,
        candidate_boundaries=candidate_boundaries,
        snap_window=float(scene_overrides.get("boundary_merge_window_sec", 2.0) or 2.0),
    )
    plot_chunks = _apply_full_subtitle_plan_to_chunks(plot_chunks, full_subtitle_understanding)
    plot_chunks = normalize_time_fields_in_items(plot_chunks)
    # Boundary alignment is a legitimate authoritative-time update; refresh the runtime lock map.
    plot_chunks = refresh_authoritative_plot_map(plot_chunks, stage="01_plot_chunks_after_alignment")

    progress(56, "按剧情块抽取代表帧...")
    frame_output_dir = os.path.join(utils.temp_dir("story_frames"), utils.md5(video_path))
    os.makedirs(frame_output_dir, exist_ok=True)

    frame_records: List[Dict[str, Any]] = []
    if effective_visual_mode != "off":
        frame_records = extract_representative_frames_for_scenes(
            video_path=video_path,
            scenes=plot_chunks,
            visual_mode=effective_visual_mode,
            output_dir=frame_output_dir,
            max_frames_dialogue=1,
            max_frames_visual_only=3,
            max_frames_long_scene=3,
            long_scene_threshold=25.0,
        )
    logger.info("影视解说 M3 完成: {} 张代表帧", len(frame_records))

    progress(68, "构建剧情证据与局部理解...")
    scene_evidence = fuse_scene_evidence(
        scenes=plot_chunks,
        frame_records=frame_records,
        visual_observations={},
    )
    scene_evidence = normalize_time_fields_in_items(scene_evidence)
    _enrich_evidence(scene_evidence, plot_chunks, global_summary)
    scene_evidence = add_local_understanding(
        scene_evidence,
        api_key=text_api_key if enable_segment_llm else "",
        base_url=text_base_url if enable_segment_llm else "",
        model=text_model if enable_segment_llm else "",
    )
    # Stage-A migration gate: make local understanding explicit even when LLM is disabled.
    scene_evidence = enrich_evidence_items(scene_evidence, global_summary)
    scene_evidence = normalize_time_fields_in_items(scene_evidence)
    if use_legacy_understanding:
        scene_evidence = enrich_legacy_segment_understanding(scene_evidence)
    _audit_video_snapshot("02_scene_evidence", scene_evidence, locals())
    logger.info("影视解说 M4 完成: evidence={}", len(scene_evidence))

    progress(78, "剧情核对...")
    scene_evidence = validate_story_segments(
        scene_evidence,
        global_summary=global_summary,
        api_key=text_api_key if enable_story_validation_llm else "",
        base_url=text_base_url if enable_story_validation_llm else "",
        model=text_model if enable_story_validation_llm else "",
    )
    scene_evidence = enrich_evidence_items(scene_evidence, global_summary)
    scene_evidence = normalize_time_fields_in_items(scene_evidence)
    if use_legacy_understanding:
        scene_evidence = enrich_legacy_segment_understanding(scene_evidence)
    _audit_video_snapshot("03_story_candidates", _build_story_candidates_from_evidence(scene_evidence), locals())

    progress(79, "高光规划：LLM 候选压缩与剧情窗口规划...")
    llm_highlight_plan = _run_traced_stage(
        "04a_llm_highlight_plan",
        locals(),
        lambda: _safe_plan_story_highlights(
            scene_evidence,
            global_summary=global_summary,
            full_subtitle_understanding=full_subtitle_understanding,
            allow_llm=enable_highlight_plan_llm,
            api_key=text_api_key if enable_highlight_plan_llm else "",
            base_url=text_base_url if enable_highlight_plan_llm else "",
            model=text_model if enable_highlight_plan_llm else "",
            scene_overrides=scene_overrides,
        ),
        scene_evidence_count=len(scene_evidence or []),
        llm_enabled=bool(enable_highlight_plan_llm),
    )

    progress(80, "高光规划：应用 LLM 高光窗口...")
    apply_highlight_plan_audit_vars = locals()
    scene_evidence = _run_traced_stage(
        "04b_apply_highlight_plan",
        locals(),
        lambda: _apply_llm_highlight_plan_nonblocking(
            scene_evidence,
            full_subtitle_understanding,
            llm_highlight_plan,
            apply_highlight_plan_audit_vars,
        ),
        scene_evidence_count=len(scene_evidence or []),
        plan_policy=(llm_highlight_plan or {}).get("plan_policy"),
    )

    progress(81, "高光规划：筛出最终候选证据...")
    scene_evidence = _run_traced_stage(
        "04c_select_final_story_evidence",
        locals(),
        lambda: _select_final_story_evidence(scene_evidence),
        scene_evidence_count=len(scene_evidence or []),
    )
    scene_evidence = normalize_time_fields_in_items(scene_evidence)

    scene_cut_points: List[float] = []
    if effective_visual_mode != "off":
        progress(82, "高光规划：复用已有边界点...")
        if use_legacy_understanding:
            scene_cut_points = _run_traced_stage(
                "04d_collect_legacy_scene_cut_points",
                locals(),
                lambda: _collect_scene_cut_points(video_path, segments, scene_overrides),
                subtitle_segment_count=len(segments or []),
                cut_point_source="legacy_detect_scenes_plus_subtitles",
            )
        else:
            scene_cut_points = _run_traced_stage(
                "04d_collect_existing_scene_cut_points",
                locals(),
                lambda: _collect_scene_cut_points_from_existing(
                    plot_chunks=plot_chunks,
                    video_boundary_candidates=video_boundary_candidates,
                    subtitle_segments=segments,
                ),
                plot_chunk_count=len(plot_chunks or []),
                video_boundary_candidate_count=len(video_boundary_candidates or []),
                subtitle_segment_count=len(segments or []),
                cut_point_source="existing_plot_chunks_video_boundaries_subtitles",
            )

    progress(83, "高光选择：typed highlight pools...")
    story_highlights = _run_traced_stage(
        "04e_extract_story_highlights",
        locals(),
        lambda: select_story_highlights_with_legacy_priority(
            scene_evidence=scene_evidence,
            scene_cut_points=scene_cut_points,
            highlight_selectivity=highlight_selectivity,
            full_subtitle_understanding=full_subtitle_understanding,
            llm_highlight_plan=llm_highlight_plan,
        )[0] if use_legacy_understanding else _extract_story_highlights(
            scene_evidence,
            scene_cut_points,
            highlight_selectivity=highlight_selectivity,
        ),
        scene_evidence_count=len(scene_evidence or []),
        scene_cut_point_count=len(scene_cut_points or []),
        highlight_selectivity=highlight_selectivity,
    )
    story_highlights = normalize_time_fields_in_items(story_highlights)
    _audit_video_snapshot("05_selected_highlights", story_highlights, locals())

    highlight_frame_records: List[Dict[str, Any]] = []
    if highlight_only and story_highlights and effective_visual_mode != "off":
        progress(84, "为高光片段抽取代表帧...")
        highlight_frame_output_dir = os.path.join(utils.temp_dir("story_highlight_frames"), utils.md5(video_path))
        os.makedirs(highlight_frame_output_dir, exist_ok=True)
        highlight_frame_records = _run_traced_stage(
            "05a_extract_highlight_frames",
            locals(),
            lambda: extract_representative_frames_for_scenes(
                video_path=video_path,
                scenes=_prepare_highlight_frame_targets(story_highlights),
                visual_mode=effective_visual_mode,
                output_dir=highlight_frame_output_dir,
                max_frames_dialogue=3,
                max_frames_visual_only=4,
                max_frames_long_scene=4,
                long_scene_threshold=18.0,
            ),
            highlight_count=len(story_highlights or []),
        )
        logger.info("高光片段代表帧抽取完成: {} 张", len(highlight_frame_records))

    highlight_narration_segments = _run_traced_stage(
        "05b_build_highlight_narration_evidence",
        locals(),
        lambda: _build_highlight_narration_segments(
            story_highlights=story_highlights,
            scene_evidence=scene_evidence,
            highlight_frame_records=highlight_frame_records,
            global_summary=global_summary,
        ),
        highlight_count=len(story_highlights or []),
        scene_evidence_count=len(scene_evidence or []),
    )
    highlight_narration_segments = enrich_evidence_items(highlight_narration_segments, global_summary)
    highlight_narration_segments = normalize_time_fields_in_items(highlight_narration_segments)
    stage_a_completeness = evaluate_evidence_items(highlight_narration_segments)
    _audit_pipeline_marker("06a_evidence_completeness", stage_a_completeness, locals())
    full_subtitle_understanding = _ensure_full_subtitle_highlight_windows(
        full_subtitle_understanding=full_subtitle_understanding,
        llm_highlight_plan=llm_highlight_plan,
        story_highlights=story_highlights,
    )
    global_summary["full_subtitle_understanding"] = full_subtitle_understanding
    if full_subtitle_understanding.get("highlight_windows_backfilled"):
        logger.warning(
            "整字幕高光窗口缺失，已使用后续链路结果回填: source={}, count={}",
            full_subtitle_understanding.get("highlight_windows_source"),
            len(full_subtitle_understanding.get("highlight_windows") or []),
        )

    progress(88, "生成影视解说脚本..." if not highlight_only else "生成高光解说脚本...")

    # 正式逻辑：高光模式也必须走成熟的大模型解说链路。
    # highlight_only 只改变送入解说器的证据范围，不允许用 _build_highlight_only_script()
    # 把字幕 text 直接复制成 narration。
    if use_legacy_understanding:
        narration_evidence = highlight_narration_segments if highlight_only else scene_evidence
    else:
        narration_evidence = _select_narration_evidence_for_generation(
            [] if highlight_only else scene_evidence,
            highlight_narration_segments,
        )
    narration_evidence = normalize_time_fields_in_items(narration_evidence)

    if effective_visual_mode != "off":
        progress(88, "视觉理解：为解说片段补充画面证据...")
        narration_evidence = _run_traced_stage(
            "06b_enrich_narration_visual_cards",
            locals(),
            # Old Native Runtime per-highlight visual-card LLM enrichment is
            # disabled in the active mainflow. Selected-highlight visual facts
            # are prepared by selected_highlight_visual_evidence_workflow.
            lambda: narration_evidence,
            narration_evidence_count=len(narration_evidence or []),
            visual_mode=effective_visual_mode,
        )
        narration_evidence = normalize_time_fields_in_items(narration_evidence)
    _audit_video_snapshot("06_scene_evidence_for_narration", narration_evidence, locals())

    try:
        progress(89, "解说生成：正式 narration engine...")
        if use_legacy_understanding and highlight_only:
            script_items = _run_traced_stage(
                "07a_generate_legacy_highlight_script",
                locals(),
                lambda: _build_highlight_only_script(highlight_narration_segments),
                narration_evidence_count=len(narration_evidence or []),
                narration_llm_mode="legacy_highlight_only_script",
            )
        else:
            script_items = _run_traced_stage(
                "07a_generate_narration",
                locals(),
                lambda: _generate_narration_with_mode(
                    narration_evidence,
                    mode=("full" if use_legacy_understanding and has_llm else narration_llm_mode),
                    max_llm_segments=narration_llm_max_segments,
                    api_key=text_api_key,
                    base_url=text_base_url,
                    model=text_model,
                    style=style or "general",
                    video_title=video_title,
                ),
                narration_evidence_count=len(narration_evidence or []),
                narration_llm_mode=("legacy_full" if use_legacy_understanding and has_llm else narration_llm_mode),
                max_llm_segments=narration_llm_max_segments,
            )
    except Exception as exc:
        _audit_pipeline_marker("07_narration_generation_error", {
            "error": str(exc),
            "mode": narration_llm_mode,
            "narration_evidence_count": len(narration_evidence or []),
            "hint": "real_narration_generation_failed_no_silent_fallback",
        }, locals())
        logger.exception("正式 LLM 解说生成失败，已写入 07_narration_generation_error，不再静默回退: {}", exc)
        raise
    script_items = normalize_time_fields_in_items(script_items)
    if not script_items:
        raise ValueError("未生成有效脚本片段")

    script_items = _force_direct_cut_script_contract(script_items)
    direct_cut_first_mode = any(_is_direct_cut_first_item(item) for item in script_items or [])

    _audit_video_snapshot("07_narration_script_raw", script_items, locals())

    if effective_visual_mode != "off" and not direct_cut_first_mode:
        progress(91, "视觉理解：根据画面证据改写解说...")
        script_items = _run_traced_stage(
            "07b_refine_narration_with_visual_cards",
            locals(),
            lambda: refine_script_items_with_visual_cards(script_items, narration_evidence, global_summary),
            script_items_count=len(script_items or []),
            narration_evidence_count=len(narration_evidence or []),
            visual_mode=effective_visual_mode,
        )
        script_items = normalize_time_fields_in_items(script_items)
        _audit_video_snapshot("07b_narration_script_visual_refined", script_items, locals())
        try:
            visual_audit_dir = os.path.dirname(output_script_path) if output_script_path else ""
            if visual_audit_dir:
                write_visual_audit_files(visual_audit_dir, narration_evidence, script_items)
        except Exception as exc:
            logger.warning("视觉解说审计文件写入失败: {}", exc)

    # Stage-H 收口：把之前 A-G 的抽样/契约校验升级为正式最终脚本门禁。
    # 这里不再把逻辑塞回 subtitle_first_pipeline.py，而是交给
    # movie_story.narration_finalize 负责：归一化、回贴语义窗、按高光过滤、
    # grounding 校验与安全修复元数据。
    if direct_cut_first_mode:
        _audit_pipeline_marker(
            "07b_refine_narration_skipped_direct_cut_first",
            {
                "script_items": len(script_items or []),
                "rule": "subtitle_time_to_original_video",
                "audio_mode": "raw",
            },
            locals(),
        )
        script_items = ensure_script_shape(script_items)
        script_items = _force_direct_cut_script_contract(script_items)
        narration_finalize_report = {
            "pipeline": "direct_cut_first_subtitle_time_finalize",
            "movie_story_strategy": movie_story_strategy,
            "script_items": len(script_items or []),
            "scene_cut_points": len(scene_cut_points or []),
            "highlight_only_mode": bool(highlight_only),
            "skipped_filters": [
                "visual_narration_refine",
                "scene_cut_alignment",
                "highlight_filter",
                "narration_finalize_repair",
            ],
            "rule": "subtitle_time_to_original_video_raw_audio",
        }
    elif use_legacy_understanding:
        if effective_visual_mode != "off":
            script_items = _align_script_items_to_scene_cuts(script_items, scene_cut_points)
        script_items = ensure_script_shape(script_items)
        script_items = _filter_script_items_by_highlights(script_items, story_highlights)
        script_items = ensure_script_shape(script_items)
        narration_finalize_report = {
            "pipeline": "legacy_subtitle_first_finalize",
            "movie_story_strategy": movie_story_strategy,
            "script_items": len(script_items or []),
            "scene_cut_points": len(scene_cut_points or []),
            "highlight_only_mode": bool(highlight_only),
        }
    else:
        script_items, narration_finalize_report = finalize_narration_script(
            script_items,
            narration_evidence=narration_evidence,
            story_highlights=story_highlights,
            scene_cut_points=scene_cut_points,
            clip_match_tolerance_seconds=float(scene_overrides.get("clip_match_tolerance_seconds", 3.0) or 3.0),
        )
    _audit_pipeline_marker("07c_final_narration_validation", narration_finalize_report, locals())
    _audit_video_snapshot("07_narration_script", script_items, locals())

    understanding_baseline_report = build_understanding_baseline_report(
        has_llm=has_llm,
        strategy=movie_story_strategy,
        full_subtitle_understanding=full_subtitle_understanding,
        global_story_understanding=global_summary,
        scene_evidence=scene_evidence,
        llm_highlight_plan=llm_highlight_plan,
        story_highlights=story_highlights,
        narration_script=script_items,
    )

    quality_issues = _validate_pipeline_quality(
        full_subtitle_understanding=full_subtitle_understanding,
        llm_highlight_plan=llm_highlight_plan,
        story_highlights=story_highlights,
        script_items=script_items,
        highlight_only=highlight_only,
        highlight_selectivity=highlight_selectivity,
        scene_evidence=scene_evidence if use_legacy_understanding else None,
        understanding_baseline_report=understanding_baseline_report if use_legacy_understanding else None,
    )

    warnings: List[str] = list(prologue_warnings) + list(tail_warnings)
    if quality_issues:
        warnings.extend([f"quality_warning:{issue}" for issue in quality_issues])
        logger.warning("影视解说质量检查警告，不中断生成: {}", "；".join(quality_issues))
    if full_subtitle_understanding.get("highlight_windows_backfilled"):
        warnings.append(f"highlight_windows_backfilled:{full_subtitle_understanding.get('highlight_windows_source')}")
    try:
        validate_script_items(script_items)
    except PreflightError as exc:
        warnings.append(str(exc))
        logger.warning("影视解说脚本预检警告: {}", exc)

    progress(96, "保存脚本文件...")
    if not output_script_path:
        video_hash = utils.md5(video_path + str(os.path.getmtime(video_path)))
        output_script_path = os.path.join(utils.script_dir(), f"{video_hash}_movie_story.json")

    understanding_baseline_report_path = write_understanding_baseline_report(
        output_script_path,
        understanding_baseline_report,
    )
    understanding_script_payload = build_understanding_script_payload(
        strategy=movie_story_strategy,
        full_subtitle_understanding=full_subtitle_understanding,
        global_story_understanding=global_summary,
        scene_evidence=scene_evidence,
        story_highlights=story_highlights,
        llm_highlight_plan=llm_highlight_plan,
        narration_script=script_items,
        understanding_baseline_report=understanding_baseline_report,
    )
    understanding_script_path = write_understanding_script(
        output_script_path,
        understanding_script_payload,
    )

    composition_plan = build_movie_story_composition_plan(
        video_path=video_path,
        movie_title=video_title,
        target_duration_seconds=int(max(float(target_minutes or 0), 0.0) * 60),
        script_items=script_items,
        narration_evidence=narration_evidence,
        story_highlights=story_highlights,
        narration_audio_path=str(scene_overrides.get("narration_audio_path", "") or ""),
        visual_mode=effective_visual_mode,
        generation_mode=generation_mode,
        metadata={
            "highlight_only_mode": bool(highlight_only),
            "narration_llm_mode": narration_llm_mode,
            "subtitle_source": sub_result.get("source", "none"),
            "subtitle_backend": sub_result.get("backend", ""),
            "migration_stage": migration_stage,
            "movie_story_strategy": movie_story_strategy,
        },
    )
    composition_plan_report = validate_composition_plan(composition_plan)
    _audit_pipeline_marker("08_movie_story_composition_plan", composition_plan_report, locals())

    os.makedirs(os.path.dirname(output_script_path), exist_ok=True)
    with open(output_script_path, "w", encoding="utf-8") as f:
        json.dump(script_items, f, ensure_ascii=False, indent=2)

    composition_plan_path = output_script_path.replace(".json", "_composition_plan.json")
    with open(composition_plan_path, "w", encoding="utf-8") as f:
        json.dump(composition_plan, f, ensure_ascii=False, indent=2)

    highlights_path = output_script_path.replace(".json", "_highlights.json")
    with open(highlights_path, "w", encoding="utf-8") as f:
        json.dump(story_highlights, f, ensure_ascii=False, indent=2)

    highlight_script_path = output_script_path.replace(".json", "_highlight_script.json")
    with open(highlight_script_path, "w", encoding="utf-8") as f:
        json.dump(script_items, f, ensure_ascii=False, indent=2)

    highlight_narration_segments_path = output_script_path.replace(".json", "_highlight_narration_segments.json")
    with open(highlight_narration_segments_path, "w", encoding="utf-8") as f:
        json.dump(highlight_narration_segments, f, ensure_ascii=False, indent=2)

    audit_path = output_script_path.replace(".json", "_audit.json")
    audit_payload = _build_story_audit_payload(
        video_path=video_path,
        subtitle_result=sub_result,
        highlight_only_mode=highlight_only,
        full_subtitle_understanding=full_subtitle_understanding,
        global_summary=global_summary,
        plot_chunks=plot_chunks,
        selected_scene_evidence=scene_evidence,
        story_highlights=story_highlights,
        highlight_narration_segments=highlight_narration_segments,
        llm_highlight_plan=llm_highlight_plan,
        script_items=script_items,
        scene_cut_points=scene_cut_points,
        video_boundary_candidates=video_boundary_candidates,
        frame_records=frame_records,
        highlight_frame_records=highlight_frame_records,
        quality_issues=quality_issues,
        warnings=warnings,
    )
    audit_payload["narration_finalize_report"] = narration_finalize_report
    audit_payload["composition_plan_report"] = composition_plan_report
    audit_payload["composition_plan_path"] = composition_plan_path
    audit_payload["understanding_baseline_report"] = understanding_baseline_report
    audit_payload["understanding_baseline_report_path"] = understanding_baseline_report_path
    audit_payload["understanding_script_path"] = understanding_script_path
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_payload, f, ensure_ascii=False, indent=2)

    if quality_issues:
        logger.warning("影视解说质量检查存在问题，但脚本已生成，继续返回成功: {}", "；".join(quality_issues))

    if any(issue in _BLOCKING_UNDERSTANDING_QUALITY_ISSUES for issue in quality_issues):
        raise ValueError("legacy_understanding_baseline_failed:" + "；".join(quality_issues))

    progress(100, "影视解说主链完成")

    return {
        "script_items": script_items,
        "script_path": output_script_path,
        "composition_script_path": highlight_script_path,
        "composition_plan": composition_plan,
        "composition_plan_path": composition_plan_path,
        "composition_plan_report": composition_plan_report,
        "composition_plan_ready": bool(composition_plan_report.get("passed")),
        "highlights_path": highlights_path,
        "highlight_script_path": highlight_script_path,
        "highlight_narration_segments_path": highlight_narration_segments_path,
        "highlight_only_ready": True,
        "highlight_only_mode": highlight_only,
        "movie_story_strategy": movie_story_strategy,
        "audit_path": audit_path,
        "evidence": scene_evidence,
        "selected_scene_evidence": scene_evidence,
        "story_highlights": story_highlights,
        "highlight_narration_segments": highlight_narration_segments,
        "narration_finalize_report": narration_finalize_report,
        "understanding_baseline_report": understanding_baseline_report,
        "understanding_baseline_report_path": understanding_baseline_report_path,
        "understanding_script": understanding_script_payload,
        "understanding_script_path": understanding_script_path,
        "full_subtitle_understanding": full_subtitle_understanding,
        "llm_highlight_plan": llm_highlight_plan,
        "global_summary": global_summary,
        "global_story_understanding": global_summary,
        "segment_local_understanding": [x.get("local_understanding") for x in scene_evidence if x.get("local_understanding")],
        "scene_evidence": scene_evidence,
        "narration_script": script_items,
        "generation_mode": generation_mode,
        "visual_mode": effective_visual_mode,
        "subtitle_path": sub_result.get("subtitle_path", ""),
        "original_subtitle_path": sub_result.get("original_subtitle_path", ""),
        "raw_subtitle_path": sub_result.get("raw_subtitle_path", ""),
        "clean_subtitle_path": sub_result.get("clean_subtitle_path", ""),
        "subtitle_segments_path": sub_result.get("subtitle_segments_path", ""),
        "subtitle_source": sub_result.get("source", "none"),
        "subtitle_backend": sub_result.get("backend", ""),
        "subtitle_regenerate": sub_result.get("regenerate", False),
        "subtitle_segments": len(segments),
        "generated_saved_subtitle_path": sub_result.get("generated_saved_path", ""),
        "generated_temp_subtitle_path": sub_result.get("generated_temp_path", ""),
        "plot_chunks": plot_chunks,
        "selected_plot_chunks": [
            chunk for chunk in plot_chunks
            if any((pkg.get("scene_id") == chunk.get("scene_id")) for pkg in scene_evidence)
        ],
        "scene_cut_points": scene_cut_points,
        "video_boundary_candidates": video_boundary_candidates,
        "video_boundary_candidate_count": len(video_boundary_candidates),
        "frame_records": frame_records,
        "highlight_frame_records": highlight_frame_records,
        "story_validation": [x.get("story_validation") for x in scene_evidence if x.get("story_validation")],
        "warnings": warnings,
        "success": True,
        "error": "",
    }


def _enrich_evidence(evidence: List[Dict], chunks: List[Dict], global_summary: Dict) -> None:
    scene_map = {s["scene_id"]: s for s in chunks}
    for pkg in evidence:
        aligned = scene_map.get(pkg.get("scene_id") or pkg.get("segment_id"), {})
        aligned_text = aligned.get("aligned_subtitle_text", "")
        if aligned_text:
            pkg["subtitle_text"] = aligned_text
        pkg["main_text_evidence"] = aligned_text
        pkg["visual_only"] = aligned.get("visual_only", False)
        pkg["evidence_mode"] = "movie_story"
        pkg["plot_role"] = aligned.get("plot_role")
        pkg["plot_function"] = aligned.get("plot_function")
        pkg["block_type"] = aligned.get("block_type")
        pkg["importance_level"] = aligned.get("importance_level")
        pkg["attraction_level"] = aligned.get("attraction_level")
        pkg["planned_char_budget"] = aligned.get("planned_char_budget")
        pkg["audio_strategy"] = aligned.get("audio_strategy")
        pkg["narration_level"] = aligned.get("narration_level")
        pkg["target_duration_minutes"] = aligned.get("target_duration_minutes")
        pkg["narrative_strategy"] = aligned.get("narrative_strategy")
        pkg["accuracy_priority"] = aligned.get("accuracy_priority")
        pkg["surface_dialogue_meaning"] = aligned.get("surface_dialogue_meaning")
        pkg["real_narrative_state"] = aligned.get("real_narrative_state")
        pkg["need_visual_verify"] = aligned.get("need_visual_verify", False)
        pkg["boundary_source"] = aligned.get("boundary_source")
        pkg["boundary_confidence"] = aligned.get("boundary_confidence")
        pkg["boundary_reasons"] = aligned.get("boundary_reasons") or []
        pkg["narrative_risk_flags"] = aligned.get("narrative_risk_flags") or []
        pkg["raw_voice_retain_suggestion"] = aligned.get("raw_voice_retain_suggestion", False)
        pkg["_global_summary"] = global_summary



def run_subtitle_first_pipeline(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Backward-compatible alias for the retired subtitle-first entry name."""
    return run_movie_story_native_engine(*args, **kwargs)


def run_native_movie_story_engine(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Native movie-story backend entry point used by movie_story.engines."""
    return run_movie_story_native_engine(*args, **kwargs)


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

