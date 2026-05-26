from __future__ import annotations

"""Direct-cut runtime for movie-story fast styles.

This path is intentionally small: after subtitles are available, it builds a
raw-audio script from subtitle time windows and returns artifacts without
entering scene detection, highlight selection, visual understanding, or
narration repair.
"""

import json
import os
from typing import Any, Callable, Dict, List

from app.services.generate_narration_script_clean import generate_narration_from_scene_evidence
from app.services.movie_story.composition_bridge import (
    build_movie_story_composition_plan,
    validate_composition_plan,
)
from app.services.movie_story.legacy_understanding_adapter import (
    build_understanding_script_payload,
    write_understanding_baseline_report,
    write_understanding_script,
)
from app.services.movie_story.quality_gate import _build_story_audit_payload
from app.services.movie_story.time_utils import normalize_time_fields_in_items
from app.services.preflight_check import validate_script_items
from app.services.script_fallback import ensure_script_shape
from app.utils import utils


DIRECT_CUT_STYLES = {"historical_drama"}


def is_direct_cut_style(style: str) -> bool:
    return str(style or "").strip().lower() in DIRECT_CUT_STYLES


def is_direct_cut_first_item(item: Dict[str, Any]) -> bool:
    return bool(item.get("direct_cut_first")) or str(item.get("generation_mode") or "") == "direct_cut_first"


def force_direct_cut_script_contract(script_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fixed: List[Dict[str, Any]] = []
    for item in script_items or []:
        row = dict(item)
        if is_direct_cut_first_item(row):
            row["direct_cut_first"] = True
            row["direct_cut_source"] = row.get("direct_cut_source") or "subtitle_time_window"
            row["generation_mode"] = "direct_cut_first"
            row["narration"] = ""
            row["OST"] = 1
            row["composition_audio_mode"] = "raw"
            row["llm_raw_voice_keep"] = True
            row["raw_voice_retain"] = True
            row["raw_voice_retain_suggestion"] = True
            row["llm_highlight_selected"] = True
            row["highlight_filter_selected"] = True
            row["narration_validation"] = {
                "status": "skipped",
                "issues": ["direct_cut_first_use_original_audio"],
            }
        fixed.append(row)
    return fixed


def _build_scene_evidence_from_subtitles(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for idx, segment in enumerate(segments or [], start=1):
        try:
            start = float(segment.get("start", 0.0) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(segment.get("end", start) or start)
        except Exception:
            end = start
        if end <= start:
            continue

        text = str(
            segment.get("text")
            or segment.get("subtitle_text")
            or segment.get("main_text_evidence")
            or ""
        ).strip()
        segment_id = str(segment.get("segment_id") or segment.get("id") or f"subtitle_{idx:04d}")
        timestamp = segment.get("timestamp") or f"{utils.format_time(start)}-{utils.format_time(end)}"
        evidence.append({
            "_id": idx,
            "segment_id": segment_id,
            "scene_id": segment_id,
            "highlight_id": segment_id,
            "highlight_rank": idx,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "timestamp": timestamp,
            "subtitle_text": text,
            "main_text_evidence": text,
            "source_text": text,
            "picture": text[:80] or "按字幕时间切原片",
            "plot_function": "历史剧快速粗切",
            "importance_level": "medium",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "llm_raw_voice_keep": True,
            "raw_voice_retain": True,
            "raw_voice_retain_suggestion": True,
            "direct_cut_source": "subtitle_segment",
        })
    return evidence


def run_direct_cut_after_subtitles(
    *,
    video_path: str,
    output_script_path: str,
    style: str,
    video_title: str,
    generation_mode: str,
    target_minutes: float,
    movie_story_strategy: str,
    migration_stage: str,
    highlight_only: bool,
    scene_overrides: Dict[str, Any],
    sub_result: Dict[str, Any],
    segments: List[Dict[str, Any]],
    progress: Callable[[int, str], None],
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> Dict[str, Any]:
    progress(18, "历史剧快速版：字幕时间直接生成裁剪脚本，跳过场景检测/高光/抽帧")

    scene_evidence = normalize_time_fields_in_items(_build_scene_evidence_from_subtitles(segments))
    if not scene_evidence:
        raise ValueError("历史剧快速版未获取到可用字幕时间轴")

    full_subtitle_understanding = {
        "subtitle_understanding_status": "direct_cut_first",
        "subtitle_input_mode": "direct_cut_first_subtitle_timeline",
        "segment_count": len(segments),
        "highlight_windows": [
            {"start": item.get("start"), "end": item.get("end"), "segment_id": item.get("segment_id")}
            for item in scene_evidence
        ],
    }
    global_summary = {
        "arc": "direct_cut_first",
        "main_storyline": "历史剧快速版：先按字幕时间轴裁剪原片，解说后续再补。",
        "video_title": video_title,
        "full_subtitle_understanding": full_subtitle_understanding,
    }
    segment_ids = [str(item.get("segment_id")) for item in scene_evidence]
    llm_highlight_plan = {
        "plan_policy": "direct_cut_first_no_highlight_filter",
        "selected_segment_ids": segment_ids,
        "raw_voice_segment_ids": segment_ids,
    }
    story_highlights = list(scene_evidence)
    highlight_narration_segments = list(scene_evidence)

    script_items = generate_narration_from_scene_evidence(
        scene_evidence=scene_evidence,
        api_key=api_key,
        base_url=base_url,
        model=model,
        style=style or "historical_drama",
        video_title=video_title,
        raw_subtitle_path=(
            sub_result.get("original_subtitle_path")
            or sub_result.get("raw_subtitle_path")
            or sub_result.get("subtitle_path")
            or ""
        ),
    )
    script_items = normalize_time_fields_in_items(force_direct_cut_script_contract(script_items))
    script_items = ensure_script_shape(script_items)
    script_items = force_direct_cut_script_contract(script_items)
    if not script_items:
        raise ValueError("历史剧快速版未生成可裁剪脚本")
    validate_script_items(script_items)

    narration_finalize_report = {
        "pipeline": "direct_cut_first_subtitle_time_finalize",
        "movie_story_strategy": movie_story_strategy,
        "script_items": len(script_items),
        "scene_cut_points": 0,
        "highlight_only_mode": bool(highlight_only),
        "skipped_filters": [
            "video_scene_detection",
            "visual_frame_extraction",
            "highlight_plan",
            "highlight_filter",
            "visual_narration_refine",
            "scene_cut_alignment",
            "narration_finalize_repair",
        ],
        "rule": "subtitle_time_to_original_video_raw_audio",
    }
    understanding_baseline_report = {
        "pipeline": "direct_cut_first_subtitle_time",
        "movie_story_strategy": movie_story_strategy,
        "status": "passed",
        "passed": True,
        "issues": [],
        "counts": {"segments": len(scene_evidence), "script_items": len(script_items)},
    }
    quality_issues: List[str] = []
    warnings: List[str] = []

    if not output_script_path:
        video_hash = utils.md5(video_path + str(os.path.getmtime(video_path)))
        output_script_path = os.path.join(utils.script_dir(), f"{video_hash}_movie_story.json")
    os.makedirs(os.path.dirname(output_script_path) or ".", exist_ok=True)

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
    understanding_script_path = write_understanding_script(output_script_path, understanding_script_payload)

    composition_plan = build_movie_story_composition_plan(
        video_path=video_path,
        movie_title=video_title,
        target_duration_seconds=int(max(float(target_minutes or 0), 0.0) * 60),
        script_items=script_items,
        narration_evidence=scene_evidence,
        story_highlights=story_highlights,
        narration_audio_path=str(scene_overrides.get("narration_audio_path", "") or ""),
        visual_mode="off",
        generation_mode=generation_mode,
        metadata={
            "highlight_only_mode": bool(highlight_only),
            "narration_llm_mode": "direct_cut_first",
            "subtitle_source": sub_result.get("source", "none"),
            "subtitle_backend": sub_result.get("backend", ""),
            "migration_stage": migration_stage,
            "movie_story_strategy": movie_story_strategy,
            "direct_cut_first": True,
        },
    )
    composition_plan_report = validate_composition_plan(composition_plan)

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
        plot_chunks=scene_evidence,
        selected_scene_evidence=scene_evidence,
        story_highlights=story_highlights,
        highlight_narration_segments=highlight_narration_segments,
        llm_highlight_plan=llm_highlight_plan,
        script_items=script_items,
        scene_cut_points=[],
        video_boundary_candidates=[],
        frame_records=[],
        highlight_frame_records=[],
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

    progress(100, "历史剧快速版完成：字幕时间直接裁剪原片")
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
        "segment_local_understanding": [],
        "scene_evidence": scene_evidence,
        "narration_script": script_items,
        "generation_mode": generation_mode,
        "visual_mode": "off",
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
        "plot_chunks": scene_evidence,
        "selected_plot_chunks": scene_evidence,
        "scene_cut_points": [],
        "video_boundary_candidates": [],
        "video_boundary_candidate_count": 0,
        "success": True,
        "warnings": warnings,
        "quality_issues": quality_issues,
        "direct_cut_first": True,
    }
