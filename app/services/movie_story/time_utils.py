from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.utils import utils


_TIME_FIELD_NAMES = (
    "start",
    "end",
    "video_start",
    "video_end",
    "semantic_start",
    "semantic_end",
    "source_start",
    "source_end",
    "subtitle_start",
    "subtitle_end",
    "story_end",
    "prologue_end",
)


def coerce_seconds(value: Any, default: float = 0.0) -> float:
    """Coerce seconds or SRT-style timecode strings into seconds."""

    if value is None:
        return float(default)
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return float(default)
    text = str(value or "").strip()
    if not text:
        return float(default)
    if "-->" in text:
        text = text.split("-->", 1)[0].strip()
    elif " - " in text:
        text = text.split(" - ", 1)[0].strip()
    elif "-" in text and ":" in text:
        text = text.split("-", 1)[0].strip()
    try:
        return float(text)
    except Exception:
        return float(utils.time_to_seconds(text) or default)


def coerce_time_pair(start: Any, end: Any, *, min_duration: float = 0.1) -> tuple[float, float]:
    s = coerce_seconds(start, 0.0)
    e = coerce_seconds(end, s + min_duration)
    if e <= s:
        e = s + min_duration
    return round(s, 3), round(e, 3)


def normalize_time_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    cur = dict(item or {})
    for key in _TIME_FIELD_NAMES:
        if key in cur and cur.get(key) not in (None, ""):
            cur[key] = round(coerce_seconds(cur.get(key), 0.0), 3)

    if ("start" in cur or "end" in cur) and cur.get("end") is not None:
        start, end = coerce_time_pair(cur.get("start", 0.0), cur.get("end", cur.get("start", 0.0)))
        cur["start"] = start
        cur["end"] = end
        cur["duration"] = round(max(end - start, 0.1), 3)
    if ("video_start" in cur or "video_end" in cur) and cur.get("video_end") is not None:
        start, end = coerce_time_pair(cur.get("video_start", cur.get("start", 0.0)), cur.get("video_end", cur.get("end", 0.0)))
        cur["video_start"] = start
        cur["video_end"] = end
    if "timestamp" not in cur and "start" in cur and "end" in cur:
        cur["timestamp"] = f"{utils.format_time(float(cur['start']))}-{utils.format_time(float(cur['end']))}"
    return cur


def normalize_time_fields_in_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalize_time_fields(item) for item in (items or []) if isinstance(item, dict)]
