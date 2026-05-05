
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story direct_runtime_v8

v8 设计原则：
- 不再用 target duration 强行切 scene。
- 场景边界优先来自“真实边界”：硬转场、字幕长停顿、时间/空间跳转词、明显空隙。
- 时长只作为 safety guard，不作为主要切分依据。
- 也就是说：
    正确边界 -> 自然形成合理时长；
    时长参数 -> 只防止极端过长或极端过碎。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from app.services.movie_story import direct_runtime_v5 as v5
from app.services.movie_story import direct_runtime_v6 as v6


def cfg_float(key: str, default: float) -> float:
    return v5.cfg_float(key, default)


def selectivity(fallback: str = "balanced") -> str:
    return v5.selectivity(fallback)


def fmt_time(seconds: float) -> str:
    return v5.fmt_time(seconds)


def resolve_video_path(kwargs=None) -> str:
    return v5.resolve_video_path(kwargs or {})


def resolve_output_script_path(kwargs=None) -> str:
    return v5.resolve_output_script_path(kwargs or {})


def audit_stage(video_path: str, output_script_path: str, stage: str, items: List[Dict[str, Any]], metadata=None):
    return v6.audit_stage(video_path, output_script_path, stage, items, metadata)


def _text_of(item: Dict[str, Any]) -> str:
    return str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")


def _reasons(item: Dict[str, Any]) -> List[str]:
    out = []
    for key in ("boundary_start_reason", "boundary_end_reason"):
        value = item.get(key) or []
        if isinstance(value, list):
            out.extend(value)
    return out


def _has_transition_word(text: str) -> bool:
    markers = [
        "第二天", "与此同时", "另一边", "回到", "几天后", "随后", "转眼",
        "晚上", "第二日", "次日", "另一头", "没过多久", "过了一会儿",
        "另一边", "与此同时", "此时"
    ]
    return any(m in text for m in markers)


def _is_hard_boundary(reasons: List[str]) -> bool:
    """
    硬边界：更接近真实场景切换。
    注意：ffmpeg_scene 只是镜头切换，不等于场景切换，不能单独切 scene。
    """
    hard_tokens = {
        "video_boundary",
        "black",
        "black_screen",
        "fade",
        "fade_in",
        "fade_out",
        "hard_transition",
        "scene_boundary",
    }
    return any(r in hard_tokens for r in reasons)


def _has_subtitle_gap(reasons: List[str]) -> bool:
    """
    字幕长停顿通常代表对话/事件暂停。
    但如果当前片段极短，可以允许合并，防止 2~4 秒碎片。
    """
    return "subtitle_gap" in reasons


def _should_merge_shot_v8(current: List[Dict[str, Any]], shot: Dict[str, Any]) -> bool:
    """
    v8 核心：
    - 不用 target duration 强切。
    - 只在真实边界处切。
    - 时长只做 safety guard。
    """
    if not current:
        return True

    scene_start = float(current[0].get("video_start", current[0].get("start", 0.0)) or 0.0)
    scene_end = float(current[-1].get("video_end", current[-1].get("end", scene_start)) or scene_start)
    shot_start = float(shot.get("video_start", shot.get("start", 0.0)) or 0.0)
    shot_end = float(shot.get("video_end", shot.get("end", shot_start)) or shot_start)

    cur_dur = max(0.0, scene_end - scene_start)
    after_dur = max(0.0, shot_end - scene_start)
    gap = max(0.0, shot_start - scene_end)

    # 这些不是“目标时长”，只是防止极端。
    min_for_split = cfg_float("movie_story_scene_boundary_min_seconds", 6.0)
    hard_max = cfg_float("movie_story_scene_hard_max_seconds", 90.0)
    max_gap = cfg_float("movie_story_scene_merge_max_gap", 2.0)

    if after_dur > hard_max:
        return False

    reasons = _reasons(shot)
    text = _text_of(shot)

    # 真硬边界：当前片段不是极短，就切。
    if _is_hard_boundary(reasons) and cur_dur >= min_for_split:
        return False

    # 字幕长停顿：当前片段达到最小可用长度，就切。
    if _has_subtitle_gap(reasons) and cur_dur >= min_for_split:
        return False

    # 时间/空间跳转词：当前片段达到最小可用长度，就切。
    if _has_transition_word(text) and cur_dur >= min_for_split:
        return False

    # 空隙过大：当前片段达到最小可用长度，就切。
    if gap > max_gap and cur_dur >= min_for_split:
        return False

    return True


def merge_shots_to_scene_candidates_v8(shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scenes: List[Dict[str, Any]] = []
    buf: List[Dict[str, Any]] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        idx = len(scenes) + 1
        s = float(buf[0].get("video_start", buf[0].get("start", 0.0)) or 0.0)
        e = float(buf[-1].get("video_end", buf[-1].get("end", s)) or s)
        text = " ".join(_text_of(x) for x in buf if _text_of(x)).strip()
        scenes.append({
            "candidate_id": f"scene_{idx:04d}",
            "candidate_type": "scene",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "subtitle_text": text,
            "source_text": text,
            "main_text_evidence": text,
            "source_shot_ids": [x.get("candidate_id") or x.get("segment_id") for x in buf],
            "children": [x.get("candidate_id") or x.get("segment_id") for x in buf],
            "boundary_start_reason": buf[0].get("boundary_start_reason") or [],
            "boundary_end_reason": buf[-1].get("boundary_end_reason") or [],
            "merge_policy": "shot_to_scene_v8_boundary_first_duration_as_guard_only",
            "stage1_policy": "movie_story_direct_v8_scene_candidates_from_shots",
        })
        buf = []

    for shot in shots or []:
        if not buf:
            buf.append(shot)
            continue
        if _should_merge_shot_v8(buf, shot):
            buf.append(shot)
        else:
            flush()
            buf.append(shot)
    flush()
    return scenes


def build_plot_chunks_v8(segments, *args, **kwargs):
    video_path = kwargs.get("video_path") or resolve_video_path(kwargs)
    output_script_path = kwargs.get("output_script_path") or resolve_output_script_path(kwargs)

    shot_candidates = v5.build_plot_chunks_v5(segments, *args, **kwargs)
    for idx, shot in enumerate(shot_candidates, start=1):
        shot["candidate_id"] = shot.get("candidate_id") or f"shot_{idx:04d}"
        shot["candidate_type"] = "shot"

    audit_stage(video_path, output_script_path, "01_shot_candidates_v8", shot_candidates, {
        "note": "shot pool from v5; this layer should be accurate and can be 400+"
    })

    scene_candidates = merge_shots_to_scene_candidates_v8(shot_candidates)
    audit_stage(video_path, output_script_path, "02_scene_candidates_v8", scene_candidates, {
        "policy": "boundary first; duration is only safety guard; no target duration split"
    })

    chunks = []
    for idx, item in enumerate(scene_candidates, start=1):
        s = float(item["video_start"])
        e = float(item["video_end"])
        seg_id = f"plot_{idx:03d}"
        cur = dict(item)
        cur.update({
            "segment_id": seg_id,
            "scene_id": seg_id,
            "candidate_id": item.get("candidate_id") or seg_id,
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
        })
        chunks.append(cur)

    logger.warning("movie_story direct v8 stage1: shots=%s scenes=%s returned_chunks=%s", len(shot_candidates), len(scene_candidates), len(chunks))
    return chunks


def select_story_highlights_v8(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    return v6.select_story_highlights_v6(
        scene_evidence,
        segments=segments,
        video_path=video_path,
        output_script_path=output_script_path,
        target_minutes=target_minutes,
        highlight_selectivity=highlight_selectivity,
    )
