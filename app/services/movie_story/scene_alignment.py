from __future__ import annotations

"""Scene boundary collection and time-window alignment helpers.

These helpers keep semantic narration/highlight windows aligned to existing
subtitle and visual cut points without re-scanning the full video unnecessarily.
"""

from typing import Any, Dict, List, Tuple

from app.services.scene_builder import detect_scenes_from_video
from app.services.movie_story.story_window import _ranges_overlap
from app.utils import utils


def _collect_scene_cut_points(video_path: str, segments: List[Dict], scene_overrides: Dict[str, Any]) -> List[float]:
    scenes = detect_scenes_from_video(
        video_path=video_path,
        subtitle_segments=segments or [],
        threshold=float(scene_overrides.get("scene_threshold", 27.0) or 27.0),
        min_scene_len=float(scene_overrides.get("min_scene_len", 2.0) or 2.0),
        force_split_gap=float(scene_overrides.get("force_split_gap", 4.0) or 4.0),
        micro_threshold=float(scene_overrides.get("micro_threshold", 2.0) or 2.0),
        min_scene_duration=float(scene_overrides.get("min_scene_duration", 1.5) or 1.5),
    )
    points = set()
    for scene in scenes or []:
        try:
            points.add(round(float(scene.get("start", 0.0) or 0.0), 3))
            points.add(round(float(scene.get("end", 0.0) or 0.0), 3))
        except Exception:
            continue
    return sorted(points)


def _collect_scene_cut_points_from_existing(
    *,
    plot_chunks: List[Dict[str, Any]],
    video_boundary_candidates: List[Dict[str, Any]],
    subtitle_segments: List[Dict[str, Any]],
) -> List[float]:
    """Collect scene cut points from work already performed earlier in the pipeline.

    The old implementation called detect_scenes_from_video() again after
    03_story_candidates.  On long real videos this second full-video scan made
    the job look stuck before 05_selected_highlights.  The cut points are not a
    new inference target here; they are just snap candidates for later alignment,
    so reusing the authoritative timeline and the already-built visual boundary
    pool is the correct hard fix.
    """
    points = set()

    def add(value: Any) -> None:
        try:
            if value is None or value == "":
                return
            points.add(round(float(value), 3))
        except Exception:
            return

    for item in plot_chunks or []:
        if not isinstance(item, dict):
            continue
        add(item.get("video_start", item.get("start")))
        add(item.get("video_end", item.get("end")))
        add(item.get("semantic_start"))
        add(item.get("semantic_end"))

    for item in video_boundary_candidates or []:
        if not isinstance(item, dict):
            continue
        add(item.get("time"))
        add(item.get("timestamp"))
        add(item.get("start"))
        add(item.get("end"))

    for item in subtitle_segments or []:
        if not isinstance(item, dict):
            continue
        add(item.get("start"))
        add(item.get("end"))

    return sorted(x for x in points if x >= 0.0)


def _snap_time_to_cut(target: float, cut_points: List[float], *, window: float, direction: str) -> tuple[float, float | None]:
    if not cut_points:
        return round(target, 3), None

    if direction == "backward":
        candidates = [p for p in cut_points if target - window <= p <= target]
        if not candidates:
            candidates = [p for p in cut_points if abs(p - target) <= window]
    elif direction == "forward":
        candidates = [p for p in cut_points if target <= p <= target + window]
        if not candidates:
            candidates = [p for p in cut_points if abs(p - target) <= window]
    else:
        candidates = [p for p in cut_points if abs(p - target) <= window]

    if not candidates:
        nearest = min(cut_points, key=lambda p: abs(p - target))
        return round(target, 3), round(abs(nearest - target), 3)

    snapped = min(candidates, key=lambda p: abs(p - target))
    return round(snapped, 3), round(abs(snapped - target), 3)


def _build_scene_intervals(cut_points: List[float]) -> List[tuple[float, float]]:
    ordered = sorted({round(float(x), 3) for x in (cut_points or [])})
    if len(ordered) < 2:
        return []
    intervals: List[tuple[float, float]] = []
    for idx in range(len(ordered) - 1):
        start = ordered[idx]
        end = ordered[idx + 1]
        if end > start:
            intervals.append((start, end))
    return intervals


def _align_range_to_scene_group(
    start: float,
    end: float,
    cut_points: List[float],
    *,
    lead_window: float,
    tail_window: float,
    hard_start_floor: float | None = None,
    hard_end_ceiling: float | None = None,
) -> Dict[str, Any]:
    def _apply_hard_bounds(result: Dict[str, Any]) -> Dict[str, Any]:
        cur = dict(result)
        floor = round(float(hard_start_floor or 0.0), 3) if hard_start_floor is not None else None
        ceiling = round(float(hard_end_ceiling or 0.0), 3) if hard_end_ceiling is not None else None
        cur["start"] = round(float(cur.get("start", semantic_start) or semantic_start), 3)
        cur["end"] = round(float(cur.get("end", semantic_end) or semantic_end), 3)
        if floor is not None:
            cur["start"] = round(max(cur["start"], floor), 3)
        if ceiling is not None:
            cur["end"] = round(min(cur["end"], ceiling), 3)
        if cur["end"] <= cur["start"]:
            fallback_end = semantic_end
            if ceiling is not None:
                fallback_end = min(fallback_end, ceiling)
            cur["end"] = round(max(cur["start"] + 0.5, fallback_end), 3)

        clipped_ranges = []
        for left, right in cur.get("scene_group_ranges") or []:
            clipped_left = round(float(left or 0.0), 3)
            clipped_right = round(float(right or clipped_left), 3)
            if floor is not None:
                clipped_left = round(max(clipped_left, floor), 3)
            if ceiling is not None:
                clipped_right = round(min(clipped_right, ceiling), 3)
            if clipped_right > clipped_left:
                clipped_ranges.append([clipped_left, clipped_right])

        cur["scene_group_ranges"] = clipped_ranges
        cur["scene_group_count"] = len(clipped_ranges)
        if cur.get("scene_group_mode") == "scene_group" and not clipped_ranges:
            cur["scene_group_mode"] = "cut_snap_fallback"
        return cur

    semantic_start = round(float(start or 0.0), 3)
    semantic_end = round(float(end or semantic_start), 3)
    if semantic_end <= semantic_start:
        semantic_end = round(semantic_start + 0.5, 3)

    intervals = _build_scene_intervals(cut_points)
    if not intervals:
        return _apply_hard_bounds({
            "start": semantic_start,
            "end": semantic_end,
            "scene_group_count": 0,
            "scene_group_ranges": [],
            "scene_group_mode": "semantic_keep",
        })

    target_left = semantic_start - max(float(lead_window or 0.0), 0.0)
    target_right = semantic_end + max(float(tail_window or 0.0), 0.0)
    overlapping = [
        (left, right)
        for left, right in intervals
        if _ranges_overlap(left, right, target_left, target_right, 0.0)
    ]
    if not overlapping:
        snapped_start, _ = _snap_time_to_cut(semantic_start, cut_points, window=max(lead_window, 2.0), direction="backward")
        snapped_end, _ = _snap_time_to_cut(semantic_end, cut_points, window=max(tail_window, 2.0), direction="forward")
        if snapped_end <= snapped_start:
            snapped_end = round(max(snapped_start + 0.5, semantic_end), 3)
        return _apply_hard_bounds({
            "start": snapped_start,
            "end": snapped_end,
            "scene_group_count": 0,
            "scene_group_ranges": [],
            "scene_group_mode": "cut_snap_fallback",
        })

    aligned_start = round(min(x[0] for x in overlapping), 3)
    aligned_end = round(max(x[1] for x in overlapping), 3)
    return _apply_hard_bounds({
        "start": aligned_start,
        "end": aligned_end,
        "scene_group_count": len(overlapping),
        "scene_group_ranges": [[round(left, 3), round(right, 3)] for left, right in overlapping],
        "scene_group_mode": "scene_group",
    })


def _parse_script_time_range_from_text(raw: Any) -> tuple[float | None, float | None]:
    text = str(raw or "").strip()
    if not text or "-" not in text:
        return None, None
    left, right = text.split("-", 1)
    try:
        start = float(utils.time_to_seconds(left.strip()))
        end = float(utils.time_to_seconds(right.strip()))
    except Exception:
        return None, None
    if end <= start:
        return None, None
    return round(start, 3), round(end, 3)


def _semantic_window_for_script_item(item: Dict[str, Any]) -> tuple[float, float]:
    """Return the original evidence window for a script item."""
    start = item.get("semantic_start")
    end = item.get("semantic_end")
    try:
        if start is not None and end is not None and float(end) > float(start):
            return round(float(start), 3), round(float(end), 3)
    except Exception:
        pass

    for key in ("semantic_timestamp", "source_timestamp", "timestamp"):
        parsed_start, parsed_end = _parse_script_time_range_from_text(item.get(key))
        if parsed_start is not None and parsed_end is not None:
            return parsed_start, parsed_end

    fallback_start = float(item.get("start", 0.0) or 0.0)
    fallback_end = float(item.get("end", fallback_start + 1.0) or (fallback_start + 1.0))
    if fallback_end <= fallback_start:
        fallback_end = fallback_start + 1.0
    return round(fallback_start, 3), round(fallback_end, 3)
