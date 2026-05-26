# -*- coding: utf-8 -*-
from __future__ import annotations

"""
two_round_visual_input_packager.py

将字幕、场景边界和视觉帧证据打包为第一轮多模态提示词材料。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "entry_points": ["build_visual_first_round_context"],
    "called_by": ["movie_story/two_round_visual_narration.py"],
    "decisions": [
        "后端视觉材料只摆事实，不提前解说或解释剧情。",
        "visual_focus_segments 只表示第一轮前详细抽帧区域。",
    ],
    "pending": ["后续可加入更稳定的 scene_boundary_context 来源。"],
    "ai_constraints": [
        "禁止在本模块生成剧情解读、主题判断、人物心理或解说式表达。",
        "禁止把 visual_focus_segments 标注为最终剪辑片段。",
    ],
}

from typing import Any, Mapping, Sequence

__all__ = ["build_visual_first_round_context"]


def build_visual_first_round_context(
    *,
    scene_segments: Sequence[Mapping[str, Any]],
    visual_focus_segments: Sequence[Mapping[str, Any]],
    low_density_keyframes: Sequence[Mapping[str, Any]],
    focus_keyframes: Sequence[Mapping[str, Any]],
) -> str:
    """Build factual visual context for the first multimodal analysis prompt."""
    _require_non_empty(scene_segments, "scene_segments")
    _require_non_empty(visual_focus_segments, "visual_focus_segments")
    _require_non_empty(low_density_keyframes, "low_density_keyframes")
    _require_non_empty(focus_keyframes, "focus_keyframes")
    blocks = [
        "【视觉证据说明】",
        "以下视觉材料只作为第一轮结构分析的客观证据，不是解说文案，也不是最终剪辑片段。",
        "visual_focus_segments 仅表示第一轮前需要详细抽帧的时间段；最终选片由双轮链提示词输出决定。",
        "请结合字幕、场景边界和关键帧判断谁在说话、谁在动作、场景里有谁、说话对象是谁。",
        "",
        _format_scene_segments(scene_segments),
        _format_visual_focus_segments(visual_focus_segments),
        _format_keyframes("【全片低密度关键帧】", low_density_keyframes),
        _format_keyframes("【视觉重点片段详细关键帧】", focus_keyframes),
    ]
    return "\n".join(block for block in blocks if block).strip()


def _format_scene_segments(scene_segments: Sequence[Mapping[str, Any]]) -> str:
    """Format factual scene windows."""
    lines = ["【场景边界 / 全片基础时间轴】"]
    for segment in scene_segments:
        lines.append(
            "- {sid}: {start:.3f}-{end:.3f}s；字幕摘录：{excerpt}".format(
                sid=_value(segment, "scene_id", "scene"),
                start=float(segment.get("start") or 0.0),
                end=float(segment.get("end") or 0.0),
                excerpt=str(segment.get("subtitle_excerpt") or "")[:160],
            )
        )
    return "\n".join(lines)


def _format_visual_focus_segments(segments: Sequence[Mapping[str, Any]]) -> str:
    """Format detailed-frame windows without calling them highlights."""
    lines = ["【第一轮视觉重点片段 / 详细抽帧区域】"]
    for segment in segments:
        lines.append(
            "- {sid}: {start:.3f}-{end:.3f}s；用途：仅用于第一轮前详细抽帧；原因：{reason}".format(
                sid=_value(segment, "visual_focus_id", "visual_focus"),
                start=float(segment.get("start") or 0.0),
                end=float(segment.get("end") or 0.0),
                reason=str(segment.get("reason") or "")[:160],
            )
        )
    return "\n".join(lines)


def _format_keyframes(title: str, keyframes: Sequence[Mapping[str, Any]]) -> str:
    """Format keyframe metadata as objective evidence."""
    lines = [title]
    for frame in keyframes:
        lines.append(
            "- frame_id={fid}；time={time:.3f}s；stage={stage}；path={path}".format(
                fid=_value(frame, "frame_id", "frame"),
                time=float(frame.get("timestamp") or 0.0),
                stage=str(frame.get("sampling_stage") or ""),
                path=str(frame.get("frame_path") or ""),
            )
        )
    return "\n".join(lines)


def _require_non_empty(items: Sequence[Mapping[str, Any]], name: str) -> None:
    """Raise when required evidence is missing."""
    if not items:
        raise ValueError(f"{name} must not be empty for two_round_visual")


def _value(record: Mapping[str, Any], key: str, default_prefix: str) -> str:
    """Read a stable display id from a metadata record."""
    value = str(record.get(key) or record.get("id") or "").strip()
    if value:
        return value
    return default_prefix
