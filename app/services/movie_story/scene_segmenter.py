# -*- coding: utf-8 -*-
from __future__ import annotations

"""Scene segmentation based on shot boundaries and subtitle windows."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "aggregate fine-grained shots into coarser scene segments",
    "called_by": ["app/services/movie_story/two_round_visual_narration.py"],
    "constraints": ["deterministic only", "no fallback"],
}

from typing import Any

from loguru import logger


def _overlap_subtitle_count(
    *,
    subtitles: list[dict[str, Any]],
    start: float,
    end: float,
) -> int:
    count = 0
    for subtitle in subtitles:
        sub_start = float(subtitle.get("start", 0.0))
        sub_end = float(subtitle.get("end", 0.0))
        if sub_end >= start and sub_start <= end:
            count += 1
    return count


def build_scene_segments(
    *,
    shot_boundaries: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    target_scene_duration_sec: float = 35.0,
    max_scene_duration_sec: float = 50.0,
    max_shots_per_scene: int = 8,
) -> list[dict[str, Any]]:
    if not shot_boundaries:
        raise ValueError("shot_boundaries is empty")
    scenes: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = [shot_boundaries[0]]
    for shot in shot_boundaries[1:]:
        start = float(current[0]["start"])
        current_end = float(current[-1]["end"])
        next_end = float(shot["end"])
        duration_if_merged = next_end - start
        too_long = duration_if_merged >= max_scene_duration_sec
        enough = current_end - start >= target_scene_duration_sec
        too_many_shots = len(current) >= max_shots_per_scene
        if too_long or (enough and too_many_shots):
            scenes.append(_build_scene(scene_index=len(scenes) + 1, shots=current, subtitles=subtitles))
            current = [shot]
            continue
        current.append(shot)
    scenes.append(_build_scene(scene_index=len(scenes) + 1, shots=current, subtitles=subtitles))
    logger.info("two_round_visual scene segmentation completed: scenes={}", len(scenes))
    return scenes


def _build_scene(
    *,
    scene_index: int,
    shots: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
) -> dict[str, Any]:
    start = float(shots[0]["start"])
    end = float(shots[-1]["end"])
    return {
        "scene_id": f"scene_{scene_index:04d}",
        "start": start,
        "end": end,
        "duration": end - start,
        "shot_ids": [str(shot["shot_id"]) for shot in shots],
        "subtitle_count": _overlap_subtitle_count(subtitles=subtitles, start=start, end=end),
    }
