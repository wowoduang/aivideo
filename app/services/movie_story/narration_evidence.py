from __future__ import annotations

"""Narration-evidence builder for movie-story highlights.

The functions in this module convert typed/high-level story highlights back into
the rich scene-evidence contract expected by the mature AIVideoGPT narration
engine.  The builder intentionally preserves plot function, local understanding,
validation hints, representative frames, raw-voice hints, and source ids instead
of copying subtitle text directly into narration.
"""

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.movie_story.story_runtime import normalize_script_items_without_retiming
from app.services.movie_story.story_window import _ranges_overlap
from app.utils import utils


def _unique_strings(values: List[Any], limit: int = 0) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def _merge_text_snippets(values: List[Any], limit: int = 4, max_chars: int = 240) -> str:
    pieces = _unique_strings(values, limit=limit)
    if not pieces:
        return ""
    return "；".join(pieces)[:max_chars].strip("；")


def _representative_frame_desc(frame_path: str, rank: int, timestamp_seconds: float | None = None) -> str:
    if timestamp_seconds is not None:
        return f"第{rank}张代表帧，时间点 {utils.format_time(float(timestamp_seconds))}"
    return f"第{rank}张代表帧，来自 {os.path.basename(frame_path)}"


def _highlight_frame_budget(highlight: Dict[str, Any]) -> int:
    start = float(highlight.get("start", 0.0) or 0.0)
    end = float(highlight.get("end", start) or start)
    duration = max(end - start, 0.1)
    if duration >= 35.0:
        return 5
    if duration >= 18.0 or str(highlight.get("importance_level") or "") == "high":
        return 4
    return 3


def _prepare_highlight_frame_targets(story_highlights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for item in story_highlights or []:
        cur = dict(item)
        highlight_id = str(cur.get("highlight_id") or "").strip()
        if not highlight_id:
            continue
        cur["scene_id"] = highlight_id
        cur["segment_id"] = highlight_id
        cur["frame_budget"] = int(cur.get("frame_budget") or _highlight_frame_budget(cur))
        targets.append(cur)
    return targets


def _build_highlight_visual_summary(
    highlight_id: str,
    highlight_frame_records: List[Dict[str, Any]],
    source_visual_summary: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    records = sorted(
        [
            dict(rec)
            for rec in (highlight_frame_records or [])
            if str(rec.get("scene_id") or rec.get("segment_id") or "").strip() == highlight_id
        ],
        key=lambda x: (
            int(x.get("rank", 0) or 0),
            float(x.get("timestamp_seconds", 0.0) or 0.0),
        ),
    )

    if records:
        visual_summary: List[Dict[str, Any]] = []
        representative_frames: List[Dict[str, Any]] = []
        for idx, rec in enumerate(records, start=1):
            frame_path = str(rec.get("frame_path") or "").strip()
            if not frame_path:
                continue
            timestamp_seconds = float(rec.get("timestamp_seconds", 0.0) or 0.0)
            desc = _representative_frame_desc(frame_path, idx, timestamp_seconds=timestamp_seconds)
            visual_summary.append(
                {
                    "frame": frame_path,
                    "desc": desc,
                    "timestamp_seconds": round(timestamp_seconds, 3),
                    "rank": int(rec.get("rank", idx) or idx),
                }
            )
            representative_frames.append(
                {
                    "frame_path": frame_path,
                    "timestamp_seconds": round(timestamp_seconds, 3),
                    "timestamp": utils.format_time(timestamp_seconds),
                    "rank": int(rec.get("rank", idx) or idx),
                    "desc": desc,
                }
            )
        return visual_summary, [x["frame_path"] for x in representative_frames], representative_frames

    fallback_visual_summary: List[Dict[str, Any]] = []
    fallback_frames: List[Dict[str, Any]] = []
    for idx, item in enumerate(source_visual_summary[:4], start=1):
        frame_path = str(item.get("frame") or item.get("frame_path") or "").strip()
        desc = str(item.get("desc") or item.get("observation") or "").strip()
        if not frame_path and not desc:
            continue
        fallback_visual_summary.append(
            {
                "frame": frame_path,
                "desc": desc or _representative_frame_desc(frame_path, idx),
                "timestamp_seconds": item.get("timestamp_seconds"),
                "rank": idx,
            }
        )
        fallback_frames.append(
            {
                "frame_path": frame_path,
                "timestamp_seconds": item.get("timestamp_seconds"),
                "timestamp": utils.format_time(float(item.get("timestamp_seconds", 0.0) or 0.0))
                if item.get("timestamp_seconds") is not None
                else "",
                "rank": idx,
                "desc": desc or _representative_frame_desc(frame_path, idx),
            }
        )
    return fallback_visual_summary, [x.get("frame_path", "") for x in fallback_frames if x.get("frame_path")], fallback_frames


def _collect_highlight_source_packages(
    highlight: Dict[str, Any],
    scene_evidence: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    highlight_segment_ids = {str(x).strip() for x in (highlight.get("segment_ids") or []) if str(x or "").strip()}
    highlight_scene_ids = {str(x).strip() for x in (highlight.get("scene_ids") or []) if str(x or "").strip()}
    highlight_start = float(highlight.get("start", 0.0) or 0.0)
    highlight_end = float(highlight.get("end", highlight_start) or highlight_start)

    matched: List[Dict[str, Any]] = []
    for pkg in scene_evidence or []:
        seg_id = str(pkg.get("segment_id") or "").strip()
        scene_id = str(pkg.get("scene_id") or "").strip()
        start = float(pkg.get("start", 0.0) or 0.0)
        end = float(pkg.get("end", start) or start)
        if (
            (seg_id and seg_id in highlight_segment_ids)
            or (scene_id and scene_id in highlight_scene_ids)
            or _ranges_overlap(start, end, highlight_start, highlight_end, 0.8)
        ):
            matched.append(dict(pkg))
    matched.sort(key=lambda x: (float(x.get("start", 0.0) or 0.0), float(x.get("end", 0.0) or 0.0)))
    return matched


def _build_highlight_story_validation(source_packages: List[Dict[str, Any]], raw_voice_keep: bool) -> Dict[str, Any]:
    validator_status = "pass"
    validator_hints: List[str] = []
    for pkg in source_packages or []:
        validation = dict(pkg.get("story_validation") or {})
        status = str(validation.get("validator_status") or "pass")
        if status == "risky":
            validator_status = "risky"
        validator_hints.extend(validation.get("validator_hints") or [])
    return {
        "validator_status": validator_status,
        "validator_hints": _unique_strings(validator_hints, limit=6),
        "raw_voice_keep": bool(raw_voice_keep),
    }


def _build_highlight_local_understanding(source_packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    core_events: List[str] = []
    emotions: List[str] = []
    characters: List[str] = []
    risk_flags: List[str] = []
    for pkg in source_packages or []:
        local = dict(pkg.get("local_understanding") or {})
        if local.get("core_event"):
            core_events.append(local["core_event"])
        if local.get("emotion"):
            emotions.append(local["emotion"])
        characters.extend(local.get("characters") or [])
        risk_flags.extend(local.get("narrative_risk_flags") or [])
    emotion_pick = _unique_strings(emotions, limit=1)
    return {
        "core_event": _merge_text_snippets(core_events, limit=3, max_chars=120),
        "emotion": emotion_pick[0] if emotion_pick else "",
        "characters": _unique_strings(characters, limit=8),
        "narrative_risk_flags": _unique_strings(risk_flags, limit=6),
    }


def _build_highlight_narration_segments(
    story_highlights: List[Dict[str, Any]],
    scene_evidence: Optional[List[Dict[str, Any]]] = None,
    highlight_frame_records: Optional[List[Dict[str, Any]]] = None,
    global_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build rich narration evidence from selected highlights.

    This is the handoff point between typed highlight selection and the legacy
    narration engine. It must not collapse highlights into raw subtitle text.
    Instead, it re-attaches the selected highlight to its source scene evidence
    so the writer still receives plot function, local understanding, validation,
    visual frames, and raw-voice hints.
    """
    scene_evidence = list(scene_evidence or [])
    highlight_frame_records = list(highlight_frame_records or [])
    global_summary = dict(global_summary or {})
    output: List[Dict[str, Any]] = []

    for idx, highlight in enumerate(story_highlights or [], start=1):
        if not isinstance(highlight, dict):
            continue
        cur_highlight = dict(highlight)
        highlight_id = str(cur_highlight.get("highlight_id") or f"highlight_{idx:03d}")
        source_packages = _collect_highlight_source_packages(cur_highlight, scene_evidence)

        source_visual_summary: List[Dict[str, Any]] = []
        for pkg in source_packages:
            source_visual_summary.extend(list(pkg.get("visual_summary") or []))
        visual_summary, frame_paths, representative_frames = _build_highlight_visual_summary(
            highlight_id,
            highlight_frame_records,
            source_visual_summary,
        )

        subtitle_text = _merge_text_snippets(
            [cur_highlight.get("source_text"), cur_highlight.get("subtitle_text"), cur_highlight.get("text")]
            + [pkg.get("subtitle_text") or pkg.get("main_text_evidence") or pkg.get("source_text") for pkg in source_packages],
            limit=8,
            max_chars=1200,
        )
        surface_dialogue_meaning = _merge_text_snippets(
            [cur_highlight.get("surface_dialogue_meaning"), cur_highlight.get("narration_hint")]
            + [pkg.get("surface_dialogue_meaning") for pkg in source_packages],
            limit=5,
            max_chars=420,
        )
        real_narrative_state = _merge_text_snippets(
            [cur_highlight.get("real_narrative_state"), cur_highlight.get("parent_story_text")]
            + [pkg.get("real_narrative_state") for pkg in source_packages],
            limit=5,
            max_chars=520,
        )
        local_understanding = _build_highlight_local_understanding(source_packages)

        plot_functions = list(cur_highlight.get("plot_functions") or [])
        if not plot_functions:
            plot_functions = _unique_strings([pkg.get("plot_function") for pkg in source_packages], limit=3)
        plot_function = str(
            cur_highlight.get("plot_function")
            or (plot_functions[0] if plot_functions else "")
            or cur_highlight.get("highlight_type")
            or cur_highlight.get("highlight_type_key")
            or "信息推进"
        )

        importance_values = [str(pkg.get("importance_level") or "") for pkg in source_packages]
        highlight_score = float(cur_highlight.get("highlight_score") or cur_highlight.get("score") or 0.0)
        importance_level = str(cur_highlight.get("importance_level") or "").strip()
        if not importance_level:
            if "high" in importance_values or highlight_score >= 0.7:
                importance_level = "high"
            elif highlight_score >= 0.4:
                importance_level = "medium"
            else:
                importance_level = "low"

        raw_voice_keep = bool(
            cur_highlight.get("raw_voice_retain")
            or cur_highlight.get("raw_voice_retain_suggestion")
            or cur_highlight.get("llm_raw_voice_keep")
            or any(pkg.get("raw_voice_retain_suggestion") or pkg.get("llm_raw_voice_keep") for pkg in source_packages)
        )
        story_validation = _build_highlight_story_validation(source_packages, raw_voice_keep)
        narrative_risk_flags = _unique_strings(
            list(local_understanding.get("narrative_risk_flags") or [])
            + [flag for pkg in source_packages for flag in list(pkg.get("narrative_risk_flags") or [])],
            limit=8,
        )
        speaker_names = _unique_strings(
            [name for pkg in source_packages for name in list(pkg.get("speaker_names") or [])],
            limit=10,
        )
        speaker_turns = max([int(pkg.get("speaker_turns", 0) or 0) for pkg in source_packages] or [0])
        exchange_pairs = []
        for pkg in source_packages:
            exchange_pairs.extend(list(pkg.get("exchange_pairs") or []))

        start = float(cur_highlight.get("start", cur_highlight.get("semantic_start", 0.0)) or 0.0)
        end = float(cur_highlight.get("end", cur_highlight.get("semantic_end", start)) or start)
        if end <= start:
            continue
        timestamp = cur_highlight.get("timestamp") or f"{utils.format_time(start)}-{utils.format_time(end)}"

        row = dict(cur_highlight)
        row.update({
            "candidate_type": "highlight_narration",
            "highlight_id": highlight_id,
            "segment_id": highlight_id,
            "scene_id": highlight_id,
            "source_scene_ids": _unique_strings(
                [pkg.get("scene_id") for pkg in source_packages]
                + list(cur_highlight.get("scene_ids") or []),
                limit=20,
            ),
            "source_segment_ids": _unique_strings(
                [pkg.get("segment_id") for pkg in source_packages]
                + list(cur_highlight.get("segment_ids") or []),
                limit=20,
            ),
            "start": round(start, 3),
            "end": round(end, 3),
            "video_start": round(float(cur_highlight.get("video_start", start) or start), 3),
            "video_end": round(float(cur_highlight.get("video_end", end) or end), 3),
            "semantic_start": round(float(cur_highlight.get("semantic_start", start) or start), 3),
            "semantic_end": round(float(cur_highlight.get("semantic_end", end) or end), 3),
            "source_start": round(start, 3),
            "source_end": round(end, 3),
            "duration": round(max(0.0, end - start), 3),
            "timestamp": timestamp,
            "semantic_timestamp": cur_highlight.get("semantic_timestamp") or timestamp,
            "source_timestamp": cur_highlight.get("source_timestamp") or timestamp,
            "subtitle_text": subtitle_text,
            "source_text": subtitle_text,
            "main_text_evidence": subtitle_text,
            "text": subtitle_text,
            "surface_dialogue_meaning": surface_dialogue_meaning or subtitle_text[:240],
            "real_narrative_state": real_narrative_state or surface_dialogue_meaning or subtitle_text[:260],
            "plot_function": plot_function,
            "plot_functions": plot_functions or [plot_function],
            "importance_level": importance_level,
            "attraction_level": cur_highlight.get("attraction_level") or ("high" if highlight_score >= 0.7 else "medium"),
            "narration_level": cur_highlight.get("narration_level") or "highlight",
            "local_understanding": local_understanding,
            "story_validation": story_validation,
            "visual_summary": visual_summary,
            "frame_paths": frame_paths,
            "representative_frames": representative_frames,
            "speaker_names": speaker_names,
            "speaker_turns": speaker_turns,
            "exchange_pairs": exchange_pairs[:12],
            "emotion_hint": cur_highlight.get("emotion_hint") or local_understanding.get("emotion") or "",
            "raw_voice_retain": raw_voice_keep,
            "raw_voice_retain_suggestion": raw_voice_keep,
            "llm_raw_voice_keep": raw_voice_keep,
            "narrative_risk_flags": narrative_risk_flags,
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "llm_highlight_reason": cur_highlight.get("llm_highlight_reason") or "typed_highlight_selection",
            "highlight_filter_reason": cur_highlight.get("highlight_filter_reason") or "typed_highlight_selection",
            "source_package_count": len(source_packages),
            "_global_summary": global_summary,
        })
        output.append(row)

    logger.warning("高光解说证据构建完成: highlights={}, narration_evidence={}", len(story_highlights or []), len(output))
    return output


def _select_narration_evidence_for_generation(
    scene_evidence: List[Dict[str, Any]],
    highlight_narration_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # 文案生成阶段只能吃最终高光证据，不能再吃完整 scene_evidence。
    # 完整 scene_evidence 中包含被 LLM 高光筛选剔除的 plot_xxx，
    # 下游 generate_narration_from_scene_evidence 会因此报“原始片段未被LLM高光选择”。
    source = list(highlight_narration_segments or [])
    source_name = "highlight_narration_segments"

    if not source:
        source = [
            dict(item)
            for item in (scene_evidence or [])
            if bool(item.get("llm_highlight_selected"))
            or bool(item.get("highlight_filter_selected"))
            or bool(item.get("raw_voice_retain"))
            or bool(item.get("llm_raw_voice_keep"))
            or str(item.get("importance_level") or "").lower() == "high"
        ]
        source_name = "filtered_scene_evidence"

    fixed: List[Dict[str, Any]] = []
    for idx, item in enumerate(source, start=1):
        row = dict(item)
        row["llm_highlight_selected"] = True
        row["highlight_filter_selected"] = True
        row.setdefault("llm_highlight_reason", source_name)
        row.setdefault("highlight_filter_reason", source_name)
        if not row.get("highlight_id"):
            row["highlight_id"] = row.get("scene_id") or row.get("segment_id") or f"highlight_gen_{idx:03d}"
        if not row.get("scene_id"):
            row["scene_id"] = row.get("highlight_id") or row.get("segment_id") or f"highlight_gen_{idx:03d}"
        if not row.get("segment_id"):
            row["segment_id"] = row.get("highlight_id") or row.get("scene_id") or f"highlight_gen_{idx:03d}"
        fixed.append(row)

    logger.warning(
        "文案生成证据输入: source={}, count={}, ids={}",
        source_name,
        len(fixed),
        [str(x.get("segment_id") or x.get("scene_id") or x.get("highlight_id")) for x in fixed[:12]],
    )
    return fixed


def _build_highlight_only_script(highlight_narration_segments, *args, **kwargs):
    """Build a conservative highlight-only script while preserving evidence metadata."""
    output: List[Dict[str, Any]] = []
    for idx, raw in enumerate(highlight_narration_segments or [], start=1):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        start = float(item.get("start", item.get("semantic_start", 0.0)) or 0.0)
        end = float(item.get("end", item.get("semantic_end", start)) or start)
        if end <= start:
            end = start + 1.0
        item.setdefault("_id", idx)
        item.setdefault("OST", idx)
        item["start"] = round(start, 3)
        item["end"] = round(end, 3)
        item.setdefault("timestamp", f"{utils.format_time(start)}-{utils.format_time(end)}")
        item.setdefault("semantic_start", round(start, 3))
        item.setdefault("semantic_end", round(end, 3))
        item.setdefault("semantic_timestamp", item["timestamp"])
        item.setdefault("narration", item.get("narration_hint") or item.get("real_narrative_state") or item.get("main_text_evidence") or item.get("subtitle_text") or "")
        item.setdefault("picture", item.get("picture") or item.get("visual_desc") or item.get("surface_dialogue_meaning") or "")
        output.append(item)
    return normalize_script_items_without_retiming(output)
