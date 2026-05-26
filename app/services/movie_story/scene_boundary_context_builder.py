# -*- coding: utf-8 -*-
from __future__ import annotations

"""
scene_boundary_context_builder.py

生成 raw_srt 第一轮可用的场景边界事实上下文。
本模块只输出客观边界和事实字段，不做剧情解读、史观判断或文案规划。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.scene_boundary_context",
    "entry_points": ["build_scene_boundary_context"],
    "called_by": ["movie_story/raw_srt_context_builder.py", "movie_story/raw_srt_two_round.py"],
    "decisions": [
        "2026-05: scene_boundary_context 只给事实，不给解读。",
        "2026-05: shot boundaries 是后端物理层材料，不直接进入 raw_srt 第一轮。",
        "2026-05: scene boundaries 是语义聚合后的上下文，目标数量通常 20-40 个。",
    ],
    "pending": ["接入真实代表帧视觉事实提取结果。", "接入正式 shot_boundary detector 输出。"],
    "ai_constraints": [
        "禁止输出 plot_function / deep_understanding / real_narrative_state 等解释字段。",
        "禁止把场景边界写成主论点或分论点。",
        "禁止把几百个 shot boundaries 直接送入 prompt。",
    ],
}

import re
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger


FORBIDDEN_INTERPRETIVE_KEYS = {
    "plot_function", "importance_level", "attraction_level", "deep_understanding",
    "real_narrative_state", "scene_function_hint", "support_type", "main_argument",
    "sub_argument", "historical_view",
}
DEFAULT_MAX_SCENE_SECONDS = 180.0


def build_scene_boundary_context(
    subtitle_segments: Sequence[Mapping[str, Any]],
    *,
    scene_candidates: Sequence[Mapping[str, Any]] | None = None,
    shot_boundaries: Sequence[Mapping[str, Any]] | None = None,
    speaker_context: Mapping[str, Any] | None = None,
    max_scene_seconds: float = DEFAULT_MAX_SCENE_SECONDS,
) -> dict[str, Any]:
    """
    生成场景边界上下文。

    意图：
        旧 scene_evidence 里混有剧情功能、重要性、局部理解等解释字段。
        raw_srt 第一轮需要的是事实上下文，因此本函数只保留边界、字幕事实、
        说话人候选、画面锚点事实等客观字段。

    注意（AI 不得修改以下行为）：
        - 不输出 FORBIDDEN_INTERPRETIVE_KEYS。
        - 不把 shot_boundaries 原样作为 prompt 输入。
        - scene_candidates 如果带解释字段，必须过滤。
    """
    source_candidates = list(scene_candidates or [])
    if not source_candidates:
        source_candidates = _build_candidates_from_subtitles(subtitle_segments, max_scene_seconds=max_scene_seconds)
    speaker_units = list((speaker_context or {}).get("speaker_units", []))
    scenes = [
        _build_scene_boundary(candidate, index=index, subtitle_segments=subtitle_segments,
                              shot_boundaries=shot_boundaries or [], speaker_units=speaker_units)
        for index, candidate in enumerate(source_candidates)
    ]
    clean_scenes = [_remove_forbidden_keys(scene) for scene in scenes]
    logger.info("场景边界上下文生成完成: scenes={}", len(clean_scenes))
    return {
        "scene_boundary_context_version": "v1",
        "scene_boundaries": clean_scenes,
        "notes": "场景边界只包含事实字段；剧情解读由 raw_srt 第一轮完成。",
    }


def _build_scene_boundary(
    candidate: Mapping[str, Any],
    *,
    index: int,
    subtitle_segments: Sequence[Mapping[str, Any]],
    shot_boundaries: Sequence[Mapping[str, Any]],
    speaker_units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """构建单个场景边界。"""
    start = _to_seconds(candidate.get("start", candidate.get("begin")))
    end = _to_seconds(candidate.get("end", candidate.get("finish")))
    subtitles = _segments_in_range(subtitle_segments, start=start, end=end)
    return {
        "scene_id": str(candidate.get("scene_id") or "scene_{:03d}".format(index + 1)),
        "start": _format_time(start),
        "end": _format_time(end),
        "duration": round(max(end - start, 0.0), 3),
        "boundary_confidence": _safe_float(candidate.get("boundary_confidence"), default=0.5),
        "shot_count": _count_shots_in_range(shot_boundaries, start=start, end=end),
        "subtitle_count": len(subtitles),
        "subtitle_keywords": _extract_keywords(subtitles),
        "speaker_candidates": _speaker_candidates_in_range(speaker_units, start=start, end=end),
        "visible_facts": _extract_visible_facts(candidate),
        "visual_anchors": _extract_visual_anchors(candidate, start=start, end=end),
    }


def _build_candidates_from_subtitles(
    subtitle_segments: Sequence[Mapping[str, Any]],
    *,
    max_scene_seconds: float,
) -> list[dict[str, Any]]:
    """在没有外部场景候选时，按字幕时间轴生成粗场景候选。"""
    candidates: list[dict[str, Any]] = []
    current: list[Mapping[str, Any]] = []
    for segment in subtitle_segments:
        if not current:
            current.append(segment)
            continue
        if _should_start_new_candidate(current, segment, max_scene_seconds=max_scene_seconds):
            candidates.append(_candidate_from_segments(current))
            current = [segment]
        else:
            current.append(segment)
    if current:
        candidates.append(_candidate_from_segments(current))
    return candidates


def _should_start_new_candidate(
    current: Sequence[Mapping[str, Any]],
    segment: Mapping[str, Any],
    *,
    max_scene_seconds: float,
) -> bool:
    """判断是否应该开始新的粗场景候选。"""
    current_start = _to_seconds(current[0].get("start"))
    current_end = _to_seconds(current[-1].get("end"))
    next_start = _to_seconds(segment.get("start"))
    return next_start - current_end > 3.0 or next_start - current_start > max_scene_seconds


def _candidate_from_segments(segments: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """由字幕段构建候选场景。"""
    return {"start": _to_seconds(segments[0].get("start")), "end": _to_seconds(segments[-1].get("end")),
            "boundary_confidence": 0.45, "visible_facts": [], "visual_anchors": []}


def _segments_in_range(subtitle_segments: Sequence[Mapping[str, Any]], *, start: float, end: float) -> list[Mapping[str, Any]]:
    """筛选时间范围内的字幕段。"""
    return [item for item in subtitle_segments if _overlap_seconds(start, end, _to_seconds(item.get("start")), _to_seconds(item.get("end"))) > 0]


def _speaker_candidates_in_range(speaker_units: Sequence[Mapping[str, Any]], *, start: float, end: float) -> list[dict[str, Any]]:
    """汇总场景内说话人候选。"""
    best_by_speaker: dict[str, dict[str, Any]] = {}
    for unit in speaker_units:
        if _overlap_seconds(start, end, _to_seconds(unit.get("start")), _to_seconds(unit.get("end"))) <= 0:
            continue
        speaker = str(unit.get("speaker") or unit.get("role_name") or "")
        if not speaker:
            continue
        confidence = _safe_float(unit.get("confidence"), default=0.0)
        if speaker not in best_by_speaker or confidence > _safe_float(best_by_speaker[speaker].get("confidence"), default=0.0):
            best_by_speaker[speaker] = {"speaker": speaker, "confidence": round(confidence, 4), "status": unit.get("status", "存疑")}
    return list(best_by_speaker.values())


def _extract_visible_facts(candidate: Mapping[str, Any]) -> list[str]:
    """提取候选场景中的客观可见事实。"""
    facts = candidate.get("visible_facts") or candidate.get("facts") or []
    if isinstance(facts, str):
        facts = [facts]
    return [str(fact).strip() for fact in facts if str(fact).strip() and not _looks_interpretive(str(fact))][:8]


def _extract_visual_anchors(candidate: Mapping[str, Any], *, start: float, end: float) -> list[dict[str, Any]]:
    """提取场景中的客观画面锚点。"""
    anchors = candidate.get("visual_anchors") or candidate.get("anchors") or []
    if not isinstance(anchors, list):
        return []
    clean: list[dict[str, Any]] = []
    for item in anchors:
        if not isinstance(item, Mapping):
            continue
        time_value = _to_seconds(item.get("time"))
        fact = str(item.get("fact") or item.get("description") or "").strip()
        if start <= time_value <= end and fact and not _looks_interpretive(fact):
            clean.append({"time": _format_time(time_value), "fact": fact, "confidence": _safe_float(item.get("confidence"), default=0.5)})
    return clean[:6]


def _extract_keywords(subtitles: Sequence[Mapping[str, Any]]) -> list[str]:
    """从字幕文本中提取轻量关键词。"""
    text = " ".join(str(item.get("text") or item.get("content") or "") for item in subtitles)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}", text)
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return [word for word, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]]


def _count_shots_in_range(shot_boundaries: Sequence[Mapping[str, Any]], *, start: float, end: float) -> int:
    """统计场景范围内的镜头边界数量。"""
    count = 0
    for item in shot_boundaries:
        shot_start = _to_seconds(item.get("start", item.get("time")))
        shot_end = _to_seconds(item.get("end", shot_start))
        if _overlap_seconds(start, end, shot_start, shot_end) > 0 or start <= shot_start <= end:
            count += 1
    return count


def _remove_forbidden_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    """递归移除解释性字段。"""
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key in FORBIDDEN_INTERPRETIVE_KEYS:
            continue
        if isinstance(item, Mapping):
            clean[key] = _remove_forbidden_keys(item)
        elif isinstance(item, list):
            clean[key] = [_remove_forbidden_keys(child) if isinstance(child, Mapping) else child for child in item]
        else:
            clean[key] = item
    return clean


def _looks_interpretive(text: str) -> bool:
    """判断文本是否明显带有解读色彩。"""
    return any(marker in text for marker in ("揭示", "说明", "体现", "象征", "适合", "主论点", "分论点", "阶层", "权力结构"))


def _overlap_seconds(start: float, end: float, other_start: float, other_end: float) -> float:
    """计算两个时间段重叠秒数。"""
    if end <= start or other_end <= other_start:
        return 0.0
    return max(0.0, min(end, other_end) - max(start, other_start))


def _to_seconds(value: Any) -> float:
    """把秒数或时间字符串转成秒。"""
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except ValueError:
        return 0.0


def _format_time(value: Any) -> str:
    """格式化秒数为 HH:MM:SS,mmm。"""
    seconds = max(_to_seconds(value), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, secs, millis)


def _safe_float(value: Any, *, default: float) -> float:
    """安全转 float。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
