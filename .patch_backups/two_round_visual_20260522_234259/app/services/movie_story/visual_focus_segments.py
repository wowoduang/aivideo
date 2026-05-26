# -*- coding: utf-8 -*-
from __future__ import annotations

"""
visual_focus_segments.py

选择 first-round multimodal prompt 前需要详细抽帧的视觉重点片段。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "entry_points": ["build_visual_focus_segments", "build_scene_segments_from_raw_srt"],
    "called_by": ["movie_story/two_round_visual_narration.py"],
    "decisions": [
        "visual_focus_segments 不是 AI 推荐高光，也不是最终剪辑片段。",
        "本模块只决定第一轮多模态提示词前哪些时间段需要详细抽帧。",
        "用户可在重跑前传入 manual/request segments 补选被模型误判的人物关系片段。",
    ],
    "pending": [
        "后续可迁移 native 中稳定的镜头切分/场景切分工具作为候选召回输入。",
    ],
    "ai_constraints": [
        "禁止把 visual_focus_segments 当作最终 script/output segments。",
        "禁止调用 legacy/native 主流程；只能迁移确定性工具能力。",
        "无法解析字幕或无法生成视觉重点片段时必须 raise，不 fallback。",
    ],
}

import json
import re
from typing import Any, Mapping

from loguru import logger

__all__ = [
    "build_scene_segments_from_raw_srt",
    "build_visual_focus_segments",
    "parse_srt_units",
]

_SRT_BLOCK_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})"
    r"\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})"
    r"(?P<body>.*?)(?=\n\s*\d+\s*\n\s*\d{1,2}:|\Z)",
    re.DOTALL,
)

_DIALOGUE_TOKENS = (
    "你", "我", "他", "她", "谁", "为什么", "怎么", "什么", "回来", "出去", "杀", "走", "说",
)


def parse_srt_units(raw_srt_text: str) -> list[dict[str, Any]]:
    """Parse SRT subtitle units into start/end/text records."""
    text = str(raw_srt_text or "").replace("\r\n", "\n").replace("\r", "\n")
    units: list[dict[str, Any]] = []
    for match in _SRT_BLOCK_RE.finditer(text):
        body = _clean_subtitle_text(match.group("body"))
        if not body:
            continue
        start = _to_seconds(match.group("start"))
        end = _to_seconds(match.group("end"))
        if end <= start:
            continue
        units.append({"start": start, "end": end, "text": body})
    if not units:
        raise ValueError("raw_srt_text contains no parseable SRT subtitle units")
    return units


def build_scene_segments_from_raw_srt(
    raw_srt_text: str,
    *,
    target_scene_seconds: float = 90.0,
    max_scene_seconds: float = 150.0,
) -> list[dict[str, Any]]:
    """Build coarse scene segments from subtitle chronology when no detector output exists."""
    units = parse_srt_units(raw_srt_text)
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    start = float(units[0]["start"])
    for unit in units:
        current.append(unit)
        duration = float(unit["end"]) - start
        if duration >= target_scene_seconds or duration >= max_scene_seconds:
            segments.append(_make_scene_segment(len(segments) + 1, current, start, float(unit["end"])))
            current = []
            start = float(unit["end"])
    if current:
        segments.append(_make_scene_segment(len(segments) + 1, current, start, float(current[-1]["end"])))
    if not segments:
        raise ValueError("failed to build scene segments from raw_srt_text")
    return segments


def build_visual_focus_segments(
    raw_srt_text: str,
    request: Mapping[str, Any],
    *,
    max_segments: int = 6,
    min_duration_seconds: float = 30.0,
    max_duration_seconds: float = 90.0,
) -> list[dict[str, Any]]:
    """Build first-round visual-focus segments for detailed pre-prompt frame sampling.

    Intent:
        These records only say which time windows deserve clearer visual evidence
        before the first multimodal prompt. They are not AI-recommended highlights,
        final narration segments, or export clips.
    """
    manual_segments = _read_request_segments(request)
    if manual_segments:
        logger.info("using manual visual_focus_segments: count={}", len(manual_segments))
        return _normalize_external_segments(manual_segments, source="manual_visual_focus")

    units = parse_srt_units(raw_srt_text)
    selected = _select_dense_dialogue_windows(
        units,
        max_segments=max_segments,
        min_duration_seconds=min_duration_seconds,
        max_duration_seconds=max_duration_seconds,
    )
    if not selected:
        raise ValueError("failed to build visual_focus_segments from subtitles")
    logger.info("auto visual_focus_segments built: count={}", len(selected))
    return selected


def _read_request_segments(request: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Read manually supplied focus segments from supported request keys."""
    for key in ("visual_focus_segments", "movie_story_visual_focus_segments"):
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise TypeError(f"{key} must be a JSON list")
            return parsed
        if isinstance(value, list):
            return value
    return []


def _normalize_external_segments(
    segments: list[Mapping[str, Any]],
    *,
    source: str,
) -> list[dict[str, Any]]:
    """Normalize user/front-end supplied visual-focus segments."""
    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        start = _required_seconds(segment, "start")
        end = _required_seconds(segment, "end")
        if end <= start:
            raise ValueError(f"invalid visual_focus segment: start={start}, end={end}")
        segment_id = str(segment.get("visual_focus_id") or segment.get("id") or f"visual_focus_{index:03d}").strip()
        normalized.append(_build_focus_record(index, start, end, source, segment_id, str(segment.get("reason") or "")))
    return normalized


def _select_dense_dialogue_windows(
    units: list[dict[str, Any]],
    *,
    max_segments: int,
    min_duration_seconds: float,
    max_duration_seconds: float,
) -> list[dict[str, Any]]:
    """Select non-overlapping dialogue-heavy windows likely to need visual disambiguation."""
    candidates = [_score_window(units, index, max_duration_seconds) for index in range(len(units))]
    ranked = sorted((item for item in candidates if item["score"] > 0), key=lambda item: item["score"], reverse=True)
    selected: list[dict[str, Any]] = []
    for item in ranked:
        start = _expand_start(float(item["start"]), float(item["end"]), min_duration_seconds)
        end = _expand_end(start, float(item["end"]), min_duration_seconds)
        if any(_overlaps(start, end, float(existing["start"]), float(existing["end"])) for existing in selected):
            continue
        selected.append(_build_focus_record(len(selected) + 1, start, end, "auto_dialogue_density", "", str(item["reason"])))
        if len(selected) >= max_segments:
            break
    return sorted(selected, key=lambda item: float(item["start"]))


def _score_window(units: list[dict[str, Any]], start_index: int, max_duration_seconds: float) -> dict[str, Any]:
    """Score one subtitle window for first-round visual disambiguation value."""
    start = float(units[start_index]["start"])
    texts: list[str] = []
    end = float(units[start_index]["end"])
    for unit in units[start_index:]:
        unit_end = float(unit["end"])
        if unit_end - start > max_duration_seconds:
            break
        texts.append(str(unit["text"]))
        end = unit_end
    joined = " ".join(texts)
    token_hits = sum(joined.count(token) for token in _DIALOGUE_TOKENS)
    punctuation_hits = sum(joined.count(token) for token in ("？", "?", "！", "!"))
    score = len(texts) * 2 + len(joined) / 20.0 + token_hits * 3 + punctuation_hits * 2
    return {"start": start, "end": end, "score": score, "reason": f"dialogue_score={score:.2f}"}


def _make_scene_segment(index: int, units: list[dict[str, Any]], start: float, end: float) -> dict[str, Any]:
    """Create one coarse scene segment record."""
    excerpt = " ".join(str(unit["text"]) for unit in units[:5]).strip()
    return {
        "scene_id": f"scene_{index:03d}",
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "subtitle_excerpt": excerpt[:240],
        "source": "raw_srt_coarse_scene",
    }


def _build_focus_record(
    index: int,
    start: float,
    end: float,
    source: str,
    segment_id: str,
    reason: str,
) -> dict[str, Any]:
    """Create a visual-focus segment record with explicit non-final semantics."""
    visual_focus_id = segment_id or f"visual_focus_{index:03d}"
    return {
        "id": visual_focus_id,
        "visual_focus_id": visual_focus_id,
        "segment_id": visual_focus_id,
        "highlight_id": visual_focus_id,
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "duration": round(float(end) - float(start), 3),
        "source": source,
        "purpose": "first_round_detailed_frame_sampling_only",
        "is_final_clip": False,
        "is_ai_recommended_highlight": False,
        "reason": reason or "visual_focus_for_first_round_multimodal_context",
    }


def _clean_subtitle_text(value: str) -> str:
    """Clean subtitle body lines without adding interpretation."""
    lines = [line.strip() for line in str(value or "").split("\n")]
    kept = [line for line in lines if line and not line.isdigit()]
    return " ".join(kept).strip()


def _to_seconds(value: str) -> float:
    """Convert SRT timestamp to seconds."""
    pieces = str(value).replace(",", ".").split(":")
    if len(pieces) == 2:
        return float(pieces[0]) * 60.0 + float(pieces[1])
    if len(pieces) == 3:
        return float(pieces[0]) * 3600.0 + float(pieces[1]) * 60.0 + float(pieces[2])
    raise ValueError(f"unsupported SRT timestamp: {value}")


def _required_seconds(segment: Mapping[str, Any], key: str) -> float:
    """Read a required segment timestamp field."""
    if key not in segment:
        raise KeyError(f"visual_focus segment missing required key: {key}")
    return float(segment[key])


def _expand_start(start: float, end: float, min_duration_seconds: float) -> float:
    """Expand window start backward to meet the minimum duration when possible."""
    duration = end - start
    if duration >= min_duration_seconds:
        return start
    return max(0.0, start - (min_duration_seconds - duration) / 2.0)


def _expand_end(start: float, end: float, min_duration_seconds: float) -> float:
    """Expand window end forward to meet the minimum duration."""
    return max(end, start + min_duration_seconds)


def _overlaps(start: float, end: float, other_start: float, other_end: float) -> bool:
    """Return whether two time windows overlap."""
    return max(start, other_start) < min(end, other_end)
