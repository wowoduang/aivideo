# -*- coding: utf-8 -*-
from __future__ import annotations

"""Hybrid visual/audio/subtitle-structure focus selector for two_round_visual."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "choose detailed-frame regions before first-round multimodal analysis",
    "called_by": ["app/services/movie_story/two_round_visual_narration.py"],
    "decisions": [
        "visual_focus_segments are not AI recommended highlights.",
        "visual_focus_segments are not final script/editing segments.",
        "Backend may combine visual/audio/subtitle-structure signals.",
        "Backend must not do LLM-like subtitle semantic plot understanding here.",
        "Subtitle text is used only for cheap structural cues such as density, turn markers, punctuation and gaps.",
    ],
    "constraints": ["deterministic only", "no fallback", "no semantic keyword plot scoring"],
}

from typing import Any

from loguru import logger


def build_visual_focus_segments(
    *,
    scene_segments: list[dict[str, Any]],
    subtitles: list[dict[str, Any]] | None = None,
    shot_boundaries: list[dict[str, Any]] | None = None,
    audio_features: list[dict[str, Any]] | None = None,
    manual_segments: list[dict[str, Any]] | None = None,
    max_segments: int = 8,
) -> list[dict[str, Any]]:
    """Build visual focus segments from backend-cheap evidence signals.

    This selector is allowed to combine:
    - visual/timeline signals: shot density, cut score, duration, full-film coverage
    - audio signals: future activity/speaker-change features
    - subtitle-structure signals: density, gaps, turn markers, punctuation

    It intentionally does not select by semantic terms such as names, roles,
    conflict words, or plot meaning. Subtitle semantic reasoning is left to the
    first-round multimodal LLM.
    """
    return select_visual_focus_segments(
        scene_segments=scene_segments,
        subtitles=subtitles or [],
        shot_boundaries=shot_boundaries or [],
        audio_features=audio_features or [],
        manual_segments=manual_segments,
        max_segments=max_segments,
    )


def select_visual_focus_segments(
    *,
    scene_segments: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    shot_boundaries: list[dict[str, Any]],
    audio_features: list[dict[str, Any]],
    manual_segments: list[dict[str, Any]] | None = None,
    max_segments: int = 8,
) -> list[dict[str, Any]]:
    if not scene_segments:
        raise ValueError("scene_segments is empty")
    if max_segments <= 0:
        raise ValueError("max_segments must be positive")

    selected = _normalize_manual_segments(manual_segments)
    scored = _score_scene_hybrid_signals(
        scene_segments=scene_segments,
        subtitles=subtitles,
        shot_boundaries=shot_boundaries,
        audio_features=audio_features,
    )

    selected.extend(
        _select_time_coverage_candidates(
            scored=scored,
            already_selected=selected,
            remaining=max_segments - len(selected),
        )
    )
    if len(selected) < max_segments:
        selected.extend(
            _select_top_candidates(
                scored=scored,
                already_selected=selected,
                remaining=max_segments - len(selected),
            )
        )

    selected = sorted(selected[:max_segments], key=lambda item: (float(item["start"]), float(item["end"])))
    logger.info(
        "two_round_visual visual focus selection completed: segments={}, strategy=hybrid_visual_audio_subtitle_structure",
        len(selected),
    )
    return selected


def _normalize_manual_segments(manual_segments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not manual_segments:
        return []
    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(manual_segments, start=1):
        normalized.append(
            {
                "segment_id": f"focus_manual_{index:03d}",
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "source": "manual",
                "reason": "manual visual focus segment",
            }
        )
    return normalized


def _score_scene_hybrid_signals(
    *,
    scene_segments: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    shot_boundaries: list[dict[str, Any]],
    audio_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    shot_map = {str(shot.get("shot_id")): shot for shot in shot_boundaries}
    total_start = float(scene_segments[0]["start"])
    total_end = float(scene_segments[-1]["end"])
    total_duration = max(total_end - total_start, 1.0)
    scored: list[dict[str, Any]] = []

    for scene in scene_segments:
        start = float(scene["start"])
        end = float(scene["end"])
        duration = max(float(scene.get("duration", end - start)), 0.1)
        shot_ids = [str(shot_id) for shot_id in scene.get("shot_ids", [])]
        shot_count = len(shot_ids)

        shot_density = shot_count / duration
        cut_score = _scene_cut_score(shot_ids=shot_ids, shot_map=shot_map)
        duration_score = _duration_score(duration)
        position_ratio = (start - total_start) / total_duration
        coverage_bonus = _coverage_priority(position_ratio)

        subtitle_stats = _subtitle_structure_score(
            subtitles=subtitles,
            scene_start=start,
            scene_end=end,
        )
        audio_score = _audio_overlap_score(
            audio_features=audio_features,
            scene_start=start,
            scene_end=end,
        )

        score = (
            shot_density * 15.0
            + cut_score * 0.30
            + duration_score * 4.0
            + coverage_bonus
            + float(subtitle_stats["score"]) * 5.0
            + audio_score * 4.0
        )
        scored.append(
            {
                "scene": scene,
                "score": score,
                "position_ratio": position_ratio,
                "reason": (
                    f"hybrid_score={score:.2f}, shot_density={shot_density:.3f}, "
                    f"cut_score={cut_score:.2f}, duration_score={duration_score:.2f}, "
                    f"subtitle_structure={float(subtitle_stats['score']):.2f}, "
                    f"subtitle_count={int(subtitle_stats['count'])}, turn_markers={int(subtitle_stats['turn_markers'])}, "
                    f"punctuation={int(subtitle_stats['punctuation'])}, gap_score={float(subtitle_stats['gap_score']):.2f}, "
                    f"audio_score={audio_score:.2f}, position={position_ratio:.2f}"
                ),
            }
        )

    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    return scored


def _subtitle_structure_score(
    *,
    subtitles: list[dict[str, Any]],
    scene_start: float,
    scene_end: float,
) -> dict[str, float | int]:
    scene_subtitles = [
        item for item in subtitles
        if float(item.get("end", 0.0)) >= scene_start and float(item.get("start", 0.0)) <= scene_end
    ]
    scene_duration = max(scene_end - scene_start, 0.1)
    count = len(scene_subtitles)
    density = min(count / scene_duration, 0.8)
    text = " ".join(str(item.get("text", "")) for item in scene_subtitles)
    char_density = min(len(text) / scene_duration / 25.0, 1.0)
    turn_markers = text.count(":") + text.count("：") + text.count("「") + text.count("」") + text.count("“") + text.count("”")
    punctuation = text.count("？") + text.count("?") + text.count("！") + text.count("!")
    gap_score = _subtitle_gap_score(scene_subtitles)
    score = density * 1.8 + char_density * 0.8 + min(turn_markers, 6) * 0.12 + min(punctuation, 6) * 0.10 + gap_score
    return {
        "score": min(score, 3.0),
        "count": count,
        "turn_markers": turn_markers,
        "punctuation": punctuation,
        "gap_score": gap_score,
    }


def _subtitle_gap_score(scene_subtitles: list[dict[str, Any]]) -> float:
    if len(scene_subtitles) < 2:
        return 0.0
    gaps: list[float] = []
    ordered = sorted(scene_subtitles, key=lambda item: float(item.get("start", 0.0)))
    for previous, current in zip(ordered, ordered[1:]):
        previous_end = float(previous.get("end", 0.0))
        current_start = float(current.get("start", 0.0))
        gap = max(current_start - previous_end, 0.0)
        gaps.append(gap)
    if not gaps:
        return 0.0
    short_pause_count = sum(1 for gap in gaps if 0.2 <= gap <= 2.5)
    return min(short_pause_count / max(len(gaps), 1), 1.0)


def _scene_cut_score(*, shot_ids: list[str], shot_map: dict[str, dict[str, Any]]) -> float:
    scores: list[float] = []
    for shot_id in shot_ids:
        shot = shot_map.get(shot_id)
        if not shot:
            continue
        scores.append(float(shot.get("cut_score", 0.0)))
    if not scores:
        return 0.0
    return sum(scores) / float(len(scores))


def _duration_score(duration: float) -> float:
    if duration < 8.0:
        return 0.3
    if duration <= 45.0:
        return 1.0
    if duration <= 90.0:
        return 0.7
    return 0.35


def _coverage_priority(position_ratio: float) -> float:
    if position_ratio <= 0.12:
        return 2.5
    if position_ratio >= 0.82:
        return 1.5
    return 0.6


def _audio_overlap_score(
    *,
    audio_features: list[dict[str, Any]],
    scene_start: float,
    scene_end: float,
) -> float:
    if not audio_features:
        return 0.0
    total = 0.0
    for feature in audio_features:
        start = float(feature.get("start", 0.0))
        end = float(feature.get("end", 0.0))
        overlap = max(0.0, min(scene_end, end) - max(scene_start, start))
        if overlap <= 0:
            continue
        total += overlap * float(feature.get("activity_score", feature.get("score", 1.0)))
    scene_duration = max(scene_end - scene_start, 0.1)
    return min(total / scene_duration, 3.0)


def _select_time_coverage_candidates(
    *,
    scored: list[dict[str, Any]],
    already_selected: list[dict[str, Any]],
    remaining: int,
) -> list[dict[str, Any]]:
    if remaining <= 0:
        return []
    selected: list[dict[str, Any]] = []
    for low, high in _coverage_bins():
        if len(selected) >= remaining:
            break
        candidates = [item for item in scored if low <= float(item["position_ratio"]) < high]
        candidate = _first_non_overlapping(candidates, already_selected + selected)
        if candidate:
            selected.append(_scene_to_focus_segment(candidate, sequence=len(already_selected) + len(selected) + 1))
    return selected


def _select_top_candidates(
    *,
    scored: list[dict[str, Any]],
    already_selected: list[dict[str, Any]],
    remaining: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in scored:
        if len(selected) >= remaining:
            break
        if _overlaps_any(item["scene"], already_selected + selected):
            continue
        selected.append(_scene_to_focus_segment(item, sequence=len(already_selected) + len(selected) + 1))
    return selected


def _coverage_bins() -> list[tuple[float, float]]:
    return [
        (0.00, 0.12),
        (0.12, 0.25),
        (0.25, 0.42),
        (0.42, 0.60),
        (0.60, 0.78),
        (0.78, 1.01),
    ]


def _first_non_overlapping(
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for candidate in candidates:
        if not _overlaps_any(candidate["scene"], selected):
            return candidate
    return None


def _scene_to_focus_segment(item: dict[str, Any], *, sequence: int) -> dict[str, Any]:
    scene = item["scene"]
    return {
        "segment_id": f"focus_{sequence:03d}",
        "start": float(scene["start"]),
        "end": float(scene["end"]),
        "source": "auto_hybrid_visual_audio_subtitle_structure",
        "reason": str(item["reason"]),
        "scene_id": str(scene.get("scene_id", "")),
    }


def _overlaps_any(scene: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    start = float(scene["start"])
    end = float(scene["end"])
    for item in selected:
        ratio = _overlap_ratio(
            start=start,
            end=end,
            other_start=float(item["start"]),
            other_end=float(item["end"]),
        )
        if ratio >= 0.35:
            return True
    return False


def _overlap_ratio(*, start: float, end: float, other_start: float, other_end: float) -> float:
    overlap = max(0.0, min(end, other_end) - max(start, other_start))
    duration = max(end - start, 0.01)
    return overlap / duration
