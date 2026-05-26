# -*- coding: utf-8 -*-
from __future__ import annotations

"""Build first-round multimodal evidence package for two_round_visual."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "package fact-only evidence for first-round multimodal prompt",
    "called_by": ["app/services/movie_story/two_round_visual_narration.py"],
    "constraints": ["fact-only", "no interpretation", "image-budget aware"],
}

from typing import Any


def _format_scene_context(*, scene_segments: list[dict[str, Any]]) -> str:
    lines = ["【场景边界】"]
    for scene in scene_segments:
        lines.append(
            f"- {scene['scene_id']}: {scene['start']:.2f}s - {scene['end']:.2f}s, "
            f"shots={len(scene.get('shot_ids', []))}, subtitles={scene.get('subtitle_count', 0)}"
        )
    return "\n".join(lines)


def _format_focus_context(*, focus_segments: list[dict[str, Any]]) -> str:
    lines = ["【视觉片段抽帧】"]
    for segment in focus_segments:
        lines.append(
            f"- {segment['segment_id']}: {segment['start']:.2f}s - {segment['end']:.2f}s, "
            f"source={segment.get('source', 'auto')}, reason={segment.get('reason', '')}"
        )
    return "\n".join(lines)


def _format_frame_context(*, title: str, frames: list[dict[str, Any]]) -> str:
    lines = [title]
    for frame in frames:
        segment_id = frame.get("segment_id") or frame.get("scene_id") or ""
        lines.append(
            f"- {frame['frame_id']}: timestamp={frame['timestamp']:.2f}s, "
            f"owner={segment_id}, role={frame.get('role', '')}"
        )
    return "\n".join(lines)


def build_two_round_visual_input_package(
    *,
    raw_srt_text: str,
    scene_segments: list[dict[str, Any]],
    focus_segments: list[dict[str, Any]],
    global_frames: list[dict[str, Any]],
    focus_frames: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt_context = "\n\n".join(
        [
            "【原始字幕】\n" + raw_srt_text.strip(),
            _format_scene_context(scene_segments=scene_segments),
            _format_focus_context(focus_segments=focus_segments),
            _format_frame_context(title="【全片低密度关键帧】", frames=global_frames),
            _format_frame_context(title="【视觉片段详细抽帧】", frames=focus_frames),
        ]
    )
    image_paths = [frame["path"] for frame in global_frames + focus_frames]
    return {
        "prompt_context": prompt_context,
        "image_paths": image_paths,
        "global_frames": global_frames,
        "focus_frames": focus_frames,
        "scene_segments": scene_segments,
        "focus_segments": focus_segments,
    }
