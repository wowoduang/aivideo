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
    """Build detailed-frame sampling windows from cheap backend signals."""
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
    """Select focus windows without subtitle semantic keyword scoring."""
    if not scene_segments:
        raise ValueError("scene_segments is empty")
    if max_segments <= 0:
        raise ValueError("max_segments must be positive")

    selected = _normalize_manual_segments(manual_segments)[:max_segments]
    remaining = max_segments - len(selected)
    if remaining <= 0:
        return _sort_segments(selected)

    scored = _score_scenes(
        scene_segments=scene_segments,
        subtitles=subtitles,
        shot_boundaries=shot_boundaries,
        audio_features=audio_features,
    )
    selected.extend(_select_candidates(scored=scored, selected=selected, remaining=remaining))
    selected = _sort_segments(selected[:max_segments])
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


def _score_scenes(
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
        scored.append(
            _score_one_scene(
                scene=scene,
                subtitles=subtitles,
                shot_map=shot_map,
                audio_features=audio_features,
                total_start=total_start,
                total_duration=total_duration,
            )
        )
    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    return scored


def _score_one_scene(
    *,
    scene: dict[str, Any],
    subtitles: list[dict[str, Any]],
    shot_map: dict[str, dict[str, Any]],
    audio_features: list[dict[str, Any]],
    total_start: float,
    total_duration: float,
) -> dict[str, Any]:
    start = float(scene["start"])
    end = float(scene["end"])
    duration = max(float(scene.get("duration", end - start)), 0.1)
    shot_ids = [str(shot_id) for shot_id in scene.get("shot_ids", [])]
    position_ratio = (start - total_start) / total_duration
    shot_density = len(shot_ids) / duration
    cut_score = _scene_cut_score(shot_ids=shot_ids, shot_map=shot_map)
    subtitle_score, subtitle_reason = _subtitle_structure_score(
        subtitles=subtitles,
        scene_start=start,
        scene_end=end,
    )
    audio_score = _audio_overlap_score(audio_features=audio_features, scene_start=start, scene_end=end)
    score = (
        shot_density * 15.0
        + cut_score * 0.30
        + _duration_score(duration) * 4.0
        + _coverage_priority(position_ratio)
        + subtitle_score * 5.0
        + audio_score * 4.0
    )
    return {
        "scene": scene,
        "score": score,
        "position_ratio": position_ratio,
        "reason": (
            f"hybrid_score={score:.2f}, shot_density={shot_density:.3f}, cut_score={cut_score:.2f}, "
            f"subtitle_structure={subtitle_score:.2f}, {subtitle_reason}, audio_score={audio_score:.2f}, "
            f"position={position_ratio:.2f}"
        ),
    }


def _subtitle_structure_score(
    *,
    subtitles: list[dict[str, Any]],
    scene_start: float,
    scene_end: float,
) -> tuple[float, str]:
    scene_subtitles = [
        item
        for item in subtitles
        if float(item.get("end", 0.0)) >= scene_start and float(item.get("start", 0.0)) <= scene_end
    ]
    scene_duration = max(scene_end - scene_start, 0.1)
    text = " ".join(str(item.get("text", "")) for item in scene_subtitles)
    density = min(len(scene_subtitles) / scene_duration, 0.8)
    char_density = min(len(text) / scene_duration / 25.0, 1.0)
    turn_markers = _count_turn_markers(text)
    punctuation = _count_punctuation(text)
    gap_score = _subtitle_gap_score(scene_subtitles)
    score = density * 1.8 + char_density * 0.8 + min(turn_markers, 6) * 0.12
    score += min(punctuation, 6) * 0.10 + gap_score
    reason = (
        f"subtitle_count={len(scene_subtitles)}, turn_markers={turn_markers}, "
        f"punctuation={punctuation}, gap_score={gap_score:.2f}"
    )
    return min(score, 3.0), reason


def _select_candidates(
    *,
    scored: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    remaining: int,
) -> list[dict[str, Any]]:
    if remaining <= 0:
        return []
    if remaining <= 2:
        return _select_top_candidates(scored=scored, selected=selected, remaining=remaining)
    coverage = _select_coverage_candidates(scored=scored, selected=selected, remaining=remaining)
    if len(coverage) >= remaining:
        return coverage
    coverage.extend(
        _select_top_candidates(scored=scored, selected=selected + coverage, remaining=remaining - len(coverage))
    )
    return coverage


def _select_top_candidates(
    *,
    scored: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    remaining: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in scored:
        if len(output) >= remaining:
            break
        if _overlaps_any(item["scene"], selected + output):
            continue
        output.append(_scene_to_focus_segment(item=item, sequence=len(selected) + len(output) + 1))
    return output


def _select_coverage_candidates(
    *,
    scored: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    remaining: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for low, high in _coverage_bins():
        if len(output) >= remaining:
            break
        candidates = [item for item in scored if low <= float(item["position_ratio"]) < high]
        candidate = _first_non_overlapping(candidates=candidates, selected=selected + output)
        if candidate:
            output.append(_scene_to_focus_segment(item=candidate, sequence=len(selected) + len(output) + 1))
    return output


def _first_non_overlapping(
    *,
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for candidate in candidates:
        if not _overlaps_any(candidate["scene"], selected):
            return candidate
    return None


def _scene_to_focus_segment(*, item: dict[str, Any], sequence: int) -> dict[str, Any]:
    scene = item["scene"]
    return {
        "segment_id": f"focus_{sequence:03d}",
        "start": float(scene["start"]),
        "end": float(scene["end"]),
        "source": "auto_hybrid_visual_audio_subtitle_structure",
        "reason": str(item["reason"]),
        "scene_id": str(scene.get("scene_id", "")),
    }


def _scene_cut_score(*, shot_ids: list[str], shot_map: dict[str, dict[str, Any]]) -> float:
    scores = [float(shot_map[shot_id].get("cut_score", 0.0)) for shot_id in shot_ids if shot_id in shot_map]
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
        overlap = _overlap_seconds(scene_start, scene_end, float(feature.get("start", 0.0)), float(feature.get("end", 0.0)))
        total += overlap * float(feature.get("activity_score", feature.get("score", 1.0)))
    return min(total / max(scene_end - scene_start, 0.1), 3.0)


def _subtitle_gap_score(scene_subtitles: list[dict[str, Any]]) -> float:
    if len(scene_subtitles) < 2:
        return 0.0
    ordered = sorted(scene_subtitles, key=lambda item: float(item.get("start", 0.0)))
    gaps = [max(float(curr.get("start", 0.0)) - float(prev.get("end", 0.0)), 0.0) for prev, curr in zip(ordered, ordered[1:])]
    if not gaps:
        return 0.0
    short_pause_count = sum(1 for gap in gaps if 0.2 <= gap <= 2.5)
    return min(short_pause_count / max(len(gaps), 1), 1.0)


def _overlaps_any(scene: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    start = float(scene["start"])
    end = float(scene["end"])
    for item in selected:
        ratio = _overlap_ratio(start=start, end=end, other_start=float(item["start"]), other_end=float(item["end"]))
        if ratio >= 0.35:
            return True
    return False


def _overlap_ratio(*, start: float, end: float, other_start: float, other_end: float) -> float:
    return _overlap_seconds(start, end, other_start, other_end) / max(end - start, 0.01)


def _overlap_seconds(start: float, end: float, other_start: float, other_end: float) -> float:
    return max(0.0, min(end, other_end) - max(start, other_start))


def _coverage_bins() -> list[tuple[float, float]]:
    return [(0.00, 0.12), (0.12, 0.25), (0.25, 0.42), (0.42, 0.60), (0.60, 0.78), (0.78, 1.01)]


def _count_turn_markers(text: str) -> int:
    return text.count(":") + text.count("：") + text.count("「") + text.count("」") + text.count("“") + text.count("”")


def _count_punctuation(text: str) -> int:
    return text.count("？") + text.count("?") + text.count("！") + text.count("!")


def _sort_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(segments, key=lambda item: (float(item["start"]), float(item["end"])))
