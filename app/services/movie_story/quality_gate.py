from __future__ import annotations

"""Quality gates and audit payload construction for the movie-story pipeline."""

from typing import Any, Dict, List

from app.services.movie_story.highlight_runtime import _movie_story_runtime_highlight_selectivity


def _validate_pipeline_quality(
    *,
    full_subtitle_understanding: Dict[str, Any],
    llm_highlight_plan: Dict[str, Any],
    story_highlights: List[Dict[str, Any]],
    script_items: List[Dict[str, Any]],
    highlight_only: bool,
    highlight_selectivity: str = "balanced",
) -> List[str]:
    issues: List[str] = []

    highlight_selectivity = _movie_story_runtime_highlight_selectivity(highlight_selectivity)
    highlight_windows = list(full_subtitle_understanding.get("highlight_windows") or [])
    highlight_windows_backfilled = bool(full_subtitle_understanding.get("highlight_windows_backfilled"))
    subtitle_input_mode = str(full_subtitle_understanding.get("subtitle_input_mode") or "").strip()
    subtitle_chunk_summaries = list(full_subtitle_understanding.get("subtitle_chunk_summaries") or [])
    selected_segment_ids = list(llm_highlight_plan.get("selected_segment_ids") or [])
    raw_voice_segment_ids = set(str(x) for x in (llm_highlight_plan.get("raw_voice_segment_ids") or []) if x)
    has_highlight_signals = bool(highlight_windows or selected_segment_ids or story_highlights)
    if subtitle_input_mode in ("", "timeline_digest") and not highlight_windows_backfilled and not has_highlight_signals:
        issues.append("整字幕理解未真正使用整字幕全文或分块结果")
    if subtitle_input_mode == "chunked_full_subtitle" and not subtitle_chunk_summaries and not has_highlight_signals:
        issues.append("整字幕分块理解失败，未产出有效的分块摘要")
    highlight_signal_count = max(
        len(highlight_windows),
        len(selected_segment_ids),
        len(script_items),
    )
    min_required_story_highlights = 0
    if highlight_signal_count > 0:
        if highlight_selectivity == "loose":
            min_required_story_highlights = 1
        elif highlight_selectivity == "strict":
            min_required_story_highlights = 2 if highlight_signal_count >= 2 else 1
        else:
            min_required_story_highlights = 1 if highlight_signal_count <= 4 else 2

    if not highlight_windows and not selected_segment_ids and not story_highlights:
        issues.append("整字幕理解未产出高光窗口")
    if not selected_segment_ids and not highlight_windows and not story_highlights:
        issues.append("精细段高光选择未产出入选结果")
    if len(story_highlights) < 2:
        issues.append("最终高光片段过少")

    if len(story_highlights) >= min_required_story_highlights:
        issues = [issue for issue in issues if issue != "\u6700\u7ec8\u9ad8\u5149\u7247\u6bb5\u8fc7\u5c11"]

    for item in story_highlights:
        if float(item.get("end", 0.0) or 0.0) <= float(item.get("start", 0.0) or 0.0):
            issues.append(f"高光片段时间非法: {item.get('highlight_id')}")
        if not item.get("scene_group_ranges") and item.get("scene_align_mode") != "semantic_keep":
            issues.append(f"高光片段未形成有效场景组: {item.get('highlight_id')}")

    if not highlight_only:
        if not script_items:
            issues.append("最终脚本为空")
        for item in script_items:
            seg_id = str(item.get("segment_id") or "")
            nv = item.get("narration_validation") or {}
            if nv.get("status") == "reject":
                issues.append(f"脚本包含被拒绝的解说文案: {seg_id or item.get('_id')}")
            if not item.get("llm_highlight_selected") and not item.get("highlight_filter_selected"):
                issues.append(f"脚本包含未通过高光选择的片段: {seg_id or item.get('_id')}")
            if int(item.get("OST", 2) or 2) == 1 and seg_id and seg_id not in raw_voice_segment_ids and not bool(item.get("llm_raw_voice_keep")):
                issues.append(f"原声片段未经LLM高光许可: {seg_id}")

    deduped: List[str] = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    return deduped


def _build_story_audit_payload(
    *,
    video_path: str,
    subtitle_result: Dict[str, Any],
    highlight_only_mode: bool,
    full_subtitle_understanding: Dict[str, Any],
    global_summary: Dict[str, Any],
    plot_chunks: List[Dict[str, Any]],
    selected_scene_evidence: List[Dict[str, Any]],
    story_highlights: List[Dict[str, Any]],
    highlight_narration_segments: List[Dict[str, Any]],
    llm_highlight_plan: Dict[str, Any],
    script_items: List[Dict[str, Any]],
    scene_cut_points: List[float],
    video_boundary_candidates: List[Dict[str, Any]],
    frame_records: List[Dict[str, Any]],
    highlight_frame_records: List[Dict[str, Any]],
    quality_issues: List[str],
    warnings: List[str],
) -> Dict[str, Any]:
    return {
        "pipeline": "subtitle_first_movie_story",
        "highlight_only_mode": highlight_only_mode,
        "video_path": video_path,
        "subtitle": {
            "source": subtitle_result.get("source", "none"),
            "backend": subtitle_result.get("backend", ""),
            "subtitle_path": subtitle_result.get("subtitle_path", ""),
            "original_subtitle_path": subtitle_result.get("original_subtitle_path", ""),
            "raw_subtitle_path": subtitle_result.get("raw_subtitle_path", ""),
            "clean_subtitle_path": subtitle_result.get("clean_subtitle_path", ""),
            "subtitle_segments_path": subtitle_result.get("subtitle_segments_path", ""),
        },
        "full_subtitle_understanding": full_subtitle_understanding,
        "global_summary": global_summary,
        "plot_chunks": plot_chunks,
        "selected_scene_evidence": selected_scene_evidence,
        "story_highlights": story_highlights,
        "highlight_narration_segments": highlight_narration_segments,
        "llm_highlight_plan": llm_highlight_plan,
        "script_items": script_items,
        "scene_cut_points": scene_cut_points,
        "video_boundary_candidates": video_boundary_candidates,
        "frame_records": frame_records,
        "highlight_frame_records": highlight_frame_records,
        "quality_issues": quality_issues,
        "warnings": warnings,
    }
