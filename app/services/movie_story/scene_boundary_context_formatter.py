# -*- coding: utf-8 -*-
from __future__ import annotations

"""
scene_boundary_context_formatter.py

把项目既有场景切分结果格式化为 {scene_boundary_context}。

职责：
- 接收旧 scene_builder / evidence 链路产出的 scene 时间轴。
- 按 scene.start/end 从字幕时间轴截取覆盖字幕。
- 输出给 prompt 使用的时间结构文本。

不负责：
- 不重新切场景。
- 不重新做 shot 聚合。
- 不做重点场景评分。
- 不调用 LLM。
"""

from collections.abc import Mapping, Sequence
from typing import Any

import re


def build_scene_boundary_context_payload_from_scenes(
    *,
    scene_segments: Sequence[Mapping[str, Any]],
    subtitle_segments: Sequence[Mapping[str, Any]],
    max_scene_count: int | None = None,
) -> dict[str, Any]:
    """从旧 scene 时间轴构建 scene_boundary_context payload。"""
    scenes = normalize_scene_segments(scene_segments)
    subtitles = normalize_subtitle_segments(subtitle_segments)

    if not scenes:
        raise ValueError("scene_segments 为空，无法构建 scene_boundary_context")
    if not subtitles:
        raise ValueError("subtitle_segments 为空，无法构建 scene_boundary_context")

    output_scenes = scenes if max_scene_count is None else scenes[: int(max_scene_count)]
    scene_boundaries = [scene_to_boundary_dict(scene, subtitles) for scene in output_scenes]
    context = format_scene_boundary_context(scene_boundaries)

    return {
        "scene_count": len(scene_boundaries),
        "scene_source": {
            "provider": "scene_builder",
            "scene_count_total": len(scenes),
            "scene_count_output": len(scene_boundaries),
        },
        "scene_boundaries": scene_boundaries,
        "scene_boundary_context": context,
    }


def format_scene_boundary_context(scene_boundaries: Sequence[Mapping[str, Any]]) -> str:
    """格式化 prompt 使用的 scene_boundary_context。"""
    header = (
        "【场景边界】\n"
        "以下为视频中的场景片段。每个片段包含时间范围、关键帧锚点和覆盖字幕。"
        "请只把它们作为时间结构参考，不要把边界当作剧情结论。"
    )
    blocks = [format_scene_block(scene) for scene in scene_boundaries]
    return "\n\n".join([header, *blocks]).strip()


def format_scene_block(scene: Mapping[str, Any]) -> str:
    """格式化单个 scene block。"""
    keyframes = scene.get("keyframe_candidates") or []
    keyframe_text = ", ".join(format_time(parse_time_value(item)) for item in keyframes) if keyframes else "无"
    subtitle_lines = list(scene.get("subtitle_lines") or [])

    lines = [
        f"{scene['scene_id']} | {format_time(scene['start'])}~{format_time(scene['end'])} | {int(round(float(scene['duration'])))}秒",
        f"关键帧锚点：{keyframe_text}",
        "覆盖字幕：",
    ]
    if subtitle_lines:
        lines.extend(f"  {line}" for line in subtitle_lines)
    else:
        lines.append("  无")
    return "\n".join(lines)


def scene_to_boundary_dict(scene: Mapping[str, Any], subtitles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """把旧 scene 转成 API 返回的 scene_boundary 结构。"""
    start = parse_time_value(scene.get("start"))
    end = parse_time_value(scene.get("end"))
    if end <= start:
        raise ValueError(f"scene 时间范围非法: {scene!r}")

    subtitle_lines = [
        format_subtitle_line(item)
        for item in subtitles
        if overlaps(
            parse_time_value(item.get("start")),
            parse_time_value(item.get("end")),
            start,
            end,
        )
    ]

    keyframes = normalize_keyframe_candidates(scene.get("keyframe_candidates") or [])

    return {
        "scene_id": str(scene.get("scene_id") or scene.get("id") or scene.get("segment_id") or "scene_unknown"),
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "subtitle_count": len(subtitle_lines),
        "keyframe_count": len(keyframes),
        "keyframe_candidates": keyframes,
        "subtitle_lines": subtitle_lines,
    }


def normalize_scene_segments(scene_segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """归一化旧 scene 列表，保留旧 scene_id 和 keyframe_candidates。"""
    normalized: list[dict[str, Any]] = []
    for index, scene in enumerate(scene_segments, start=1):
        if not isinstance(scene, Mapping):
            raise ValueError(f"scene_segments[{index - 1}] 必须是对象")
        try:
            start = parse_time_value(scene.get("start"))
            end = parse_time_value(scene.get("end"))
        except (TypeError, ValueError):
            raise ValueError(f"scene 缺少有效 start/end: {scene!r}") from None

        if end <= start:
            raise ValueError(f"scene 时间范围非法: {scene!r}")

        normalized.append(
            {
                "scene_id": str(scene.get("scene_id") or scene.get("id") or scene.get("segment_id") or f"scene_{index:03d}"),
                "start": start,
                "end": end,
                "keyframe_candidates": normalize_keyframe_candidates(scene.get("keyframe_candidates") or []),
            }
        )

    return sorted(normalized, key=lambda item: (item["start"], item["end"]))


def normalize_subtitle_segments(subtitle_segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """归一化字幕片段，支持秒数和 00:00:00.000 字符串。"""
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(subtitle_segments, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"subtitle_segments[{index - 1}] 必须是对象")
        try:
            start = parse_time_value(item.get("start"))
            end = parse_time_value(item.get("end"))
        except (TypeError, ValueError):
            raise ValueError(f"字幕片段缺少有效 start/end: {item!r}") from None

        if end <= start:
            raise ValueError(f"字幕时间范围非法: {item!r}")

        normalized.append(
            {
                "start": start,
                "end": end,
                "text": normalize_subtitle_text(str(item.get("text") or "")),
                "seg_id": item.get("seg_id") or item.get("id") or f"sub_{index:03d}",
            }
        )
    return sorted(normalized, key=lambda item: (item["start"], item["end"]))


def normalize_keyframe_candidates(value: Sequence[Any]) -> list[float]:
    """归一化旧 scene 的 keyframe_candidates。"""
    keyframes: list[float] = []
    for item in value:
        try:
            if isinstance(item, Mapping):
                raw = item.get("time", item.get("timestamp", item.get("start")))
            else:
                raw = item
            keyframes.append(round(parse_time_value(raw), 3))
        except (TypeError, ValueError):
            raise ValueError(f"非法 keyframe candidate: {item!r}") from None
    return sorted(dict.fromkeys(keyframes))


def format_subtitle_line(item: Mapping[str, Any]) -> str:
    """格式化一行覆盖字幕。"""
    return f"{format_time(parse_time_value(item.get('start')))}~{format_time(parse_time_value(item.get('end')))} {normalize_subtitle_text(str(item.get('text') or ''))}"


def normalize_subtitle_text(text: str) -> str:
    """清理字幕内部多余空白；中文字符之间不保留人为空格。"""
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)
    return cleaned


def parse_time_value(value: Any) -> float:
    """解析秒数或 HH:MM:SS / MM:SS 时间。"""
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty time")
    if raw.replace(".", "", 1).isdigit():
        return float(raw)

    parts = raw.replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"invalid time: {value}")


def format_time(value: Any) -> str:
    """格式化为 MM:SS。"""
    seconds = parse_time_value(value)
    total = int(round(max(0.0, seconds)))
    minutes = total // 60
    remain = total % 60
    return f"{minutes:02d}:{remain:02d}"


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    """判断两个时间段是否重叠。"""
    return max(start_a, start_b) < min(end_a, end_b)
