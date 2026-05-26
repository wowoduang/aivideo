# -*- coding: utf-8 -*-
from __future__ import annotations

"""Selection of visual focus segments for detailed first-round frame sampling."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "choose detailed-frame regions for first-round multimodal evidence",
    "called_by": ["app/services/movie_story/two_round_visual_narration.py"],
    "constraints": [
        "visual_focus_segments are not final highlights",
        "visual_focus_segments only decide where to sample detailed frames",
        "deterministic only",
    ],
}

from typing import Any

from loguru import logger


DIALOGUE_KEYWORDS = ("你", "我", "他", "她", "他们", "她们", "谁", "怎么", "为什么", "！", "?", "？")


def _subtitle_text_for_scene(
    *,
    subtitles: list[dict[str, Any]],
    start: float,
    end: float,
) -> str:
    pieces: list[str] = []
    for subtitle in subtitles:
        sub_start = float(subtitle.get("start", 0.0))
        sub_end = float(subtitle.get("end", 0.0))
        if sub_end >= start and sub_start <= end:
            pieces.append(str(subtitle.get("text", "")))
    return " ".join(pieces)


def _score_scene(*, scene: dict[str, Any], subtitles: list[dict[str, Any]]) -> tuple[float, str]:
    start = float(scene["start"])
    end = float(scene["end"])
    duration = max(float(scene.get("duration", end - start)), 1.0)
    subtitle_count = int(scene.get("subtitle_count", 0))
    text = _subtitle_text_for_scene(subtitles=subtitles, start=start, end=end)
    keyword_hits = sum(text.count(keyword) for keyword in DIALOGUE_KEYWORDS)
    density = subtitle_count / duration
    score = density * 8.0 + keyword_hits * 1.5
    reason = f"subtitle_density={density:.2f}, keyword_hits={keyword_hits}, subtitle_count={subtitle_count}"
    return score, reason


def select_visual_focus_segments(
    *,
    scene_segments: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    manual_segments: list[dict[str, Any]] | None = None,
    max_segments: int = 6,
) -> list[dict[str, Any]]:
    if not scene_segments:
        raise ValueError("scene_segments is empty")
    selected: list[dict[str, Any]] = []
    if manual_segments:
        for index, segment in enumerate(manual_segments, start=1):
            selected.append(
                {
                    "segment_id": f"focus_manual_{index:03d}",
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "source": "manual",
                    "reason": "manual visual focus segment",
                }
            )
    scored: list[tuple[float, dict[str, Any], str]] = []
    for scene in scene_segments:
        score, reason = _score_scene(scene=scene, subtitles=subtitles)
        scored.append((score, scene, reason))
    scored.sort(key=lambda item: item[0], reverse=True)
    for _, scene, reason in scored:
        if len(selected) >= max_segments:
            break
        selected.append(
            {
                "segment_id": f"focus_{len(selected) + 1:03d}",
                "start": float(scene["start"]),
                "end": float(scene["end"]),
                "source": "auto",
                "reason": reason,
                "scene_id": str(scene["scene_id"]),
            }
        )
    selected.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    logger.info("two_round_visual visual focus selection completed: segments={}", len(selected))
    return selected


def build_visual_focus_segments(
    *,
    scene_segments: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    manual_segments: list[dict[str, Any]] | None = None,
    max_segments: int = 6,
) -> list[dict[str, Any]]:
    return select_visual_focus_segments(
        scene_segments=scene_segments,
        subtitles=subtitles,
        manual_segments=manual_segments,
        max_segments=max_segments,
    )
