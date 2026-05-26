from __future__ import annotations

"""Story-window policy for the movie-story narration chain.

This module owns prologue trimming, tail/preview detection, full-subtitle
highlight window normalization, and non-destructive LLM highlight annotations.
It was extracted from ``subtitle_first_pipeline.py`` so the old entry point can
stay as a thin compatibility orchestrator.
"""

import re
from typing import Any, Dict, List

from app.utils import utils


_TAIL_PREVIEW_CUES = {
    "下集预告": 6.0,
    "下期预告": 6.0,
    "下回预告": 6.0,
    "次集预告": 6.0,
    "下周预告": 5.5,
    "精彩预告": 5.0,
    "未完待续": 4.8,
    "敬请期待": 4.2,
    "欲知后事如何": 5.2,
    "下一集": 2.4,
    "下集": 1.6,
    "下期": 1.6,
    "下回": 1.6,
    "预告": 2.4,
}
_TAIL_CREDITS_CUES = {
    "片尾曲": 6.0,
    "片尾": 3.5,
    "主题曲": 2.6,
    "职员表": 5.0,
    "演职员": 5.0,
    "演职员表": 5.4,
    "领衔主演": 2.4,
    "主演": 1.5,
    "特别出演": 2.2,
    "友情出演": 2.2,
    "联合主演": 2.2,
    "出品人": 1.8,
    "总制片人": 2.0,
    "制片人": 1.6,
    "总监制": 2.0,
    "监制": 1.4,
    "导演": 1.4,
    "编剧": 1.4,
    "摄影指导": 1.6,
    "美术指导": 1.6,
    "后期制作": 1.6,
    "鸣谢": 2.0,
}
_TAIL_BRACKET_RE = re.compile(
    r"^[\[\(【（]?(?:片尾曲|片尾|下集预告|下期预告|下回预告|精彩预告|预告)[\]\)】）]?$",
    re.IGNORECASE,
)


_PROLOGUE_CUE_ONLY_RE = re.compile(
    r"^\s*[\[\(]?\s*(?:bgm|music|applause|laughter|laughing|sigh|crying|phone ringing|ringtone|"
    r"音乐|配乐|掌声|笑声|哭声|叹气|电话铃声)\s*[\]\)]?\s*$",
    re.IGNORECASE,
)


def _unique_strings(values: List[Any], limit: int = 0) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def _split_prompt_time_range(raw: Any) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", ""
    if "-->" in text:
        left, right = text.split("-->", 1)
        return left.strip(), right.strip()
    if " - " in text:
        left, right = text.split(" - ", 1)
        return left.strip(), right.strip()
    if "-" in text and ":" in text:
        left, right = text.split("-", 1)
        return left.strip(), right.strip()
    return text, ""


def _parse_prompt_time(raw: Any, *, prefer_end: bool = False) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    left, right = _split_prompt_time_range(text)
    text = right if prefer_end and right else left
    # ``utils.time_to_seconds`` is intentionally forgiving and may return 0.0
    # after logging invalid strings.  This module needs strict boundary parsing
    # so manual invalid values can fall back to first speech/LLM boundaries.
    if not re.match(r"^(?:\d+(?:\.\d+)?|\d{1,2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)$", text):
        return None
    try:
        return round(float(utils.time_to_seconds(text)), 3)
    except Exception:
        return None


def _coerce_highlight_time(raw: Any, *, prefer_end: bool = False) -> float | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)):
        return round(float(raw), 3)
    return _parse_prompt_time(raw, prefer_end=prefer_end)


def _normalize_prompt_highlight_window(
    item: Dict[str, Any],
    *,
    default_category: str = "",
    default_importance: str = "medium",
    default_raw_voice_priority: str = "low",
    default_reason: str = "llm_highlight_window",
) -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    start = _coerce_highlight_time(item.get("start"))
    end = _coerce_highlight_time(item.get("end"))
    if start is None or end is None or end <= start:
        return None

    importance = str(item.get("importance") or default_importance or "medium").strip().lower()
    if importance not in {"high", "medium", "low"}:
        importance = default_importance
    raw_voice_priority = str(
        item.get("raw_voice_priority") or default_raw_voice_priority or "low"
    ).strip().lower()
    if raw_voice_priority not in {"high", "medium", "low"}:
        raw_voice_priority = default_raw_voice_priority

    category = str(item.get("category") or item.get("label") or default_category or "信息揭露").strip()
    reason = str(item.get("reason") or item.get("label") or category or default_reason).strip()
    return {
        "start": utils.format_time(start),
        "end": utils.format_time(end),
        "category": category,
        "importance": importance,
        "raw_voice_priority": raw_voice_priority,
        "reason": reason,
    }


def _dedupe_prompt_highlight_windows(windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    ordered = sorted(
        (item for item in windows if isinstance(item, dict)),
        key=lambda x: (_coerce_highlight_time(x.get("start")) or 0.0, _coerce_highlight_time(x.get("end")) or 0.0),
    )
    for item in ordered:
        key = (
            item.get("start"),
            item.get("end"),
            str(item.get("category") or ""),
            str(item.get("importance") or ""),
            str(item.get("raw_voice_priority") or ""),
            str(item.get("reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _resolve_highlight_category(
    reasons: List[str] | None,
    plot_functions: List[str] | None = None,
) -> str:
    candidates: List[str] = [str(x).strip() for x in (plot_functions or []) if str(x or "").strip()]
    for reason in reasons or []:
        text = str(reason or "").strip()
        if not text:
            continue
        if text.startswith("plot:"):
            candidates.insert(0, text.split(":", 1)[1].strip())
        else:
            candidates.append(text)

    for cue in ("反转", "情感爆发", "冲突升级", "人物行动", "阴谋推进", "伏笔兑现", "生死危机", "关键决定", "立场转变", "关系变化", "人物转折", "阴谋揭露", "信息揭露", "高潮", "结局收束", "结尾"):
        for item in candidates:
            if cue and cue in item:
                return cue
    return candidates[0] if candidates else ""


def _build_prompt_highlight_windows_from_story_highlights(
    story_highlights: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    windows: List[Dict[str, Any]] = []
    for item in story_highlights or []:
        reason_parts = [str(x).strip() for x in (item.get("highlight_reasons") or []) if str(x or "").strip()]
        importance = str(item.get("importance_level") or "medium").strip().lower()
        if importance not in {"high", "medium", "low"}:
            importance = "medium"
        raw_voice_priority = "high" if bool(item.get("raw_voice_retain")) else ("medium" if importance == "high" else "low")
        category = _resolve_highlight_category(reason_parts, list(item.get("plot_functions") or []))
        normalized = _normalize_prompt_highlight_window(
            {
                "start": item.get("start"),
                "end": item.get("end"),
                "category": category,
                "importance": importance,
                "raw_voice_priority": raw_voice_priority,
                "reason": " / ".join(reason_parts[:3]) or category or "story_highlights_fallback",
            },
            default_category=category or "信息揭露",
            default_importance=importance,
            default_raw_voice_priority=raw_voice_priority,
            default_reason="story_highlights_fallback",
        )
        if normalized:
            windows.append(normalized)
    return _dedupe_prompt_highlight_windows(windows)


def _ensure_full_subtitle_highlight_windows(
    *,
    full_subtitle_understanding: Dict[str, Any],
    llm_highlight_plan: Dict[str, Any],
    story_highlights: List[Dict[str, Any]],
) -> Dict[str, Any]:
    updated = dict(full_subtitle_understanding or {})
    existing_windows = _dedupe_prompt_highlight_windows(
        [
            normalized
            for normalized in (
                _normalize_prompt_highlight_window(item)
                for item in list(updated.get("highlight_windows") or [])
            )
            if normalized
        ]
    )
    if existing_windows:
        updated["highlight_windows"] = existing_windows
        updated.setdefault("highlight_windows_backfilled", False)
        updated["highlight_windows_source"] = str(updated.get("highlight_windows_source") or "llm_or_existing")
        return updated

    llm_plan_windows = _dedupe_prompt_highlight_windows(
        [
            normalized
            for normalized in (
                _normalize_prompt_highlight_window(
                    item,
                    default_importance="high",
                    default_raw_voice_priority="medium",
                    default_reason="llm_must_keep_range",
                )
                for item in list(llm_highlight_plan.get("must_keep_ranges") or [])
            )
            if normalized
        ]
    )
    if llm_plan_windows:
        updated["highlight_windows"] = llm_plan_windows
        updated["highlight_windows_backfilled"] = True
        updated["highlight_windows_source"] = "llm_plan_must_keep_ranges"
        return updated

    story_windows = _build_prompt_highlight_windows_from_story_highlights(story_highlights)
    if story_windows:
        updated["highlight_windows"] = story_windows
        updated["highlight_windows_backfilled"] = True
        updated["highlight_windows_source"] = "story_highlights_fallback"
        return updated

    updated.setdefault("highlight_windows", [])
    updated.setdefault("highlight_windows_backfilled", False)
    updated["highlight_windows_source"] = str(updated.get("highlight_windows_source") or "none")
    return updated


def _is_meaningful_speech_segment(item: Dict[str, Any]) -> bool:
    text = str(item.get("text") or item.get("subtitle_text") or "").strip()
    if not text or _PROLOGUE_CUE_ONLY_RE.match(text):
        return False
    core = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    if len(core) >= 2:
        return True
    start = float(item.get("start", 0.0) or 0.0)
    end = float(item.get("end", start) or start)
    return (end - start) >= 0.8


def _infer_first_speech_time(subtitle_segments: List[Dict[str, Any]]) -> float | None:
    for item in sorted(subtitle_segments or [], key=lambda x: float(x.get("start", 0.0) or 0.0)):
        if _is_meaningful_speech_segment(item):
            return round(float(item.get("start", 0.0) or 0.0), 3)
    return None


def _normalize_tail_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _score_tail_preview_marker(text: str, position_ratio: float) -> float:
    if not text:
        return 0.0

    score = 0.0
    for cue, weight in _TAIL_PREVIEW_CUES.items():
        if cue in text:
            score += weight

    if "预告" in text and any(cue in text for cue in ("下集", "下期", "下回", "次集", "下一集")):
        score += 2.5
    if _TAIL_BRACKET_RE.match(text) and "预告" in text:
        score += 1.2
    if position_ratio >= 0.92:
        score += 1.2
    elif position_ratio >= 0.84:
        score += 0.7
    return round(score, 3)


def _score_tail_credits_marker(text: str, position_ratio: float) -> float:
    if not text:
        return 0.0

    score = 0.0
    for cue, weight in _TAIL_CREDITS_CUES.items():
        if cue in text:
            score += weight

    if _TAIL_BRACKET_RE.match(text) and ("片尾" in text or "片尾曲" in text):
        score += 1.5
    if _PROLOGUE_CUE_ONLY_RE.match(text) and position_ratio >= 0.9:
        score += 0.8
    if position_ratio >= 0.9:
        score += 0.9
    elif position_ratio >= 0.82:
        score += 0.4
    return round(score, 3)


def _merge_tail_marker_runs(markers: List[Dict[str, Any]], gap_threshold: float = 8.0) -> List[Dict[str, Any]]:
    if not markers:
        return []

    ordered = sorted(markers, key=lambda x: (float(x.get("start", 0.0) or 0.0), -float(x.get("score", 0.0) or 0.0)))
    merged: List[Dict[str, Any]] = [dict(ordered[0])]
    for item in ordered[1:]:
        current = dict(item)
        prev = merged[-1]
        same_type = str(prev.get("type") or "") == str(current.get("type") or "")
        close_enough = float(current.get("start", 0.0) or 0.0) <= float(prev.get("end", 0.0) or 0.0) + gap_threshold
        if not (same_type and close_enough):
            merged.append(current)
            continue

        prev["end"] = round(max(float(prev.get("end", 0.0) or 0.0), float(current.get("end", 0.0) or 0.0)), 3)
        prev["score"] = round(max(float(prev.get("score", 0.0) or 0.0), float(current.get("score", 0.0) or 0.0)), 3)
        prev["source_segment_ids"] = list(
            dict.fromkeys(list(prev.get("source_segment_ids") or []) + list(current.get("source_segment_ids") or []))
        )
        prev["reason"] = " / ".join(
            dict.fromkeys(
                [str(x).strip() for x in [prev.get("reason"), current.get("reason")] if str(x or "").strip()]
            )
        )
    return merged


def _detect_tail_markers(subtitle_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(subtitle_segments or [], key=lambda x: float(x.get("start", 0.0) or 0.0))
    if not ordered:
        return {
            "story_end_seconds": None,
            "story_end_source": "none",
            "credits_start_seconds": None,
            "preview_start_seconds": None,
            "tail_markers": [],
        }

    total_duration = max(float(ordered[-1].get("end", ordered[-1].get("start", 0.0)) or 0.0), 0.0)
    if total_duration <= 0.0:
        return {
            "story_end_seconds": None,
            "story_end_source": "none",
            "credits_start_seconds": None,
            "preview_start_seconds": None,
            "tail_markers": [],
        }

    candidates: List[Dict[str, Any]] = []
    for seg in ordered:
        start = round(float(seg.get("start", 0.0) or 0.0), 3)
        end = round(float(seg.get("end", start) or start), 3)
        if end <= start:
            end = round(start + 0.5, 3)
        position_ratio = start / max(total_duration, 1.0)
        if position_ratio < 0.72:
            continue

        text = _normalize_tail_text(seg.get("text") or seg.get("subtitle_text") or "")
        if not text:
            continue

        preview_score = _score_tail_preview_marker(text, position_ratio)
        credits_score = _score_tail_credits_marker(text, position_ratio)
        if preview_score < 4.0 and credits_score < 4.2:
            continue

        marker_type = "preview" if preview_score >= credits_score else "credits"
        score = max(preview_score, credits_score)
        reason = "tail_preview_cue" if marker_type == "preview" else "tail_credits_cue"
        candidates.append(
            {
                "type": marker_type,
                "start": start,
                "end": end,
                "score": round(score, 3),
                "reason": reason,
                "source_segment_ids": [str(seg.get("seg_id") or seg.get("id") or "")],
            }
        )

    markers = _merge_tail_marker_runs(candidates)
    preview_marker = next((item for item in markers if str(item.get("type") or "") == "preview"), None)
    credits_candidates = [item for item in markers if str(item.get("type") or "") == "credits"]
    if preview_marker is not None:
        credits_candidates = [
            item for item in credits_candidates if float(item.get("start", 0.0) or 0.0) <= float(preview_marker.get("start", 0.0) or 0.0) + 1.0
        ]
    credits_marker = credits_candidates[0] if credits_candidates else None

    story_end_candidates = [
        float(item.get("start", 0.0) or 0.0)
        for item in (credits_marker, preview_marker)
        if item is not None
    ]
    story_end_seconds = min(story_end_candidates) if story_end_candidates else None
    story_end_source_parts: List[str] = []
    if credits_marker is not None:
        story_end_source_parts.append("credits_auto")
    if preview_marker is not None:
        story_end_source_parts.append("preview_auto")

    return {
        "story_end_seconds": round(float(story_end_seconds), 3) if story_end_seconds is not None else None,
        "story_end_source": "+".join(story_end_source_parts) if story_end_source_parts else "none",
        "credits_start_seconds": round(float(credits_marker.get("start", 0.0) or 0.0), 3) if credits_marker is not None else None,
        "preview_start_seconds": round(float(preview_marker.get("start", 0.0) or 0.0), 3) if preview_marker is not None else None,
        "tail_markers": markers,
    }


def _resolve_story_end_from_tail_markers(
    *,
    full_subtitle_understanding: Dict[str, Any],
    subtitle_segments: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], List[str]]:
    detected = _detect_tail_markers(subtitle_segments)
    updated = dict(full_subtitle_understanding or {})
    story_end_seconds = detected.get("story_end_seconds")
    credits_start_seconds = detected.get("credits_start_seconds")
    preview_start_seconds = detected.get("preview_start_seconds")

    updated["tail_markers"] = list(detected.get("tail_markers") or [])
    updated["resolved_story_end_source"] = str(detected.get("story_end_source") or "none")
    updated["resolved_story_end_seconds"] = story_end_seconds
    updated["story_end_time"] = utils.format_time(float(story_end_seconds)) if story_end_seconds is not None else ""
    updated["credits_start_time"] = utils.format_time(float(credits_start_seconds)) if credits_start_seconds is not None else ""
    updated["preview_start_time"] = utils.format_time(float(preview_start_seconds)) if preview_start_seconds is not None else ""
    return updated, []


def _resolve_prologue_end_from_strategy(
    *,
    full_subtitle_understanding: Dict[str, Any],
    subtitle_segments: List[Dict[str, Any]],
    scene_overrides: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    strategy = str(scene_overrides.get("prologue_strategy") or "speech_first").strip().lower()
    manual_time = str(scene_overrides.get("manual_prologue_end_time") or "").strip()
    llm_time = _parse_prompt_time(full_subtitle_understanding.get("prologue_end_time"))
    first_speech_time = _infer_first_speech_time(subtitle_segments)
    warnings: List[str] = []

    resolved_time = llm_time
    resolved_source = "llm_auto"

    if strategy == "manual_time":
        manual_seconds = _parse_prompt_time(manual_time)
        if manual_seconds is not None:
            resolved_time = manual_seconds
            resolved_source = "manual_time"
        else:
            warnings.append("manual_prologue_end_time_invalid")
            if first_speech_time is not None:
                resolved_time = first_speech_time
                resolved_source = "manual_invalid_fallback_first_speech"
            elif llm_time is not None:
                resolved_time = llm_time
                resolved_source = "manual_invalid_fallback_llm"
            else:
                resolved_source = "manual_invalid_no_boundary"
    elif strategy == "llm_auto":
        resolved_time = llm_time
        resolved_source = "llm_auto" if llm_time is not None else "llm_auto_empty"
    else:
        if first_speech_time is not None:
            resolved_time = first_speech_time
            resolved_source = "first_speech"
        elif llm_time is not None:
            resolved_time = llm_time
            resolved_source = "first_speech_fallback_llm"
        else:
            resolved_source = "first_speech_no_boundary"

    updated = dict(full_subtitle_understanding or {})
    updated["prologue_strategy"] = strategy
    updated["manual_prologue_end_time"] = manual_time
    updated["first_speech_time"] = first_speech_time
    updated["llm_prologue_end_time"] = full_subtitle_understanding.get("prologue_end_time", "")
    updated["resolved_prologue_end_source"] = resolved_source
    updated["resolved_prologue_end_seconds"] = resolved_time
    updated["prologue_end_time"] = (
        utils.format_time(float(resolved_time))
        if resolved_time is not None
        else str(full_subtitle_understanding.get("prologue_end_time") or "").strip()
    )
    return updated, warnings


def _ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float, slack: float = 1.5) -> bool:
    return max(start_a, start_b) <= min(end_a, end_b) + slack


def _clip_range_after_prologue(
    start: float,
    end: float,
    prologue_end: float | None,
    *,
    min_duration: float = 0.5,
) -> tuple[float, float, bool]:
    safe_start = round(float(start or 0.0), 3)
    safe_end = round(float(end or safe_start), 3)
    if safe_end <= safe_start:
        safe_end = round(safe_start + min_duration, 3)
    if prologue_end is None or safe_start >= prologue_end or safe_end <= prologue_end + min_duration:
        return safe_start, safe_end, False

    trimmed_start = round(max(safe_start, prologue_end), 3)
    if trimmed_start >= safe_end - min_duration:
        return safe_start, safe_end, False
    return trimmed_start, safe_end, trimmed_start > safe_start


def _build_prologue_metrics(start: float, end: float, prologue_end: float | None) -> Dict[str, Any]:
    safe_start = round(float(start or 0.0), 3)
    safe_end = round(float(end or safe_start), 3)
    if safe_end <= safe_start:
        safe_end = round(safe_start + 0.5, 3)
    duration = max(safe_end - safe_start, 0.1)

    if prologue_end is None:
        return {
            "before_prologue_end": False,
            "crosses_prologue_boundary": False,
            "prologue_overlap_duration": 0.0,
            "prologue_overlap_ratio": 0.0,
        }

    overlap = max(0.0, min(safe_end, prologue_end) - safe_start)
    return {
        "before_prologue_end": bool(safe_end <= prologue_end + 0.5),
        "crosses_prologue_boundary": bool(safe_start < prologue_end - 0.05 and safe_end > prologue_end + 0.05),
        "prologue_overlap_duration": round(overlap, 3),
        "prologue_overlap_ratio": round(min(overlap / duration, 1.0), 3),
    }


def _annotate_prologue_state(
    item: Dict[str, Any],
    prologue_end: float | None,
    *,
    trim_crossing: bool = False,
) -> Dict[str, Any]:
    cur = dict(item)
    start = float(cur.get("start", 0.0) or 0.0)
    end = float(cur.get("end", start) or start)
    original_metrics = _build_prologue_metrics(start, end, prologue_end)

    cur.setdefault("prologue_trimmed", False)
    if trim_crossing:
        trimmed_start, trimmed_end, trimmed = _clip_range_after_prologue(start, end, prologue_end)
        if trimmed:
            cur["prologue_trimmed"] = True
            cur["prologue_original_start"] = round(start, 3)
            cur["prologue_original_end"] = round(end, 3)
            cur["prologue_original_overlap_duration"] = original_metrics["prologue_overlap_duration"]
            cur["prologue_original_overlap_ratio"] = original_metrics["prologue_overlap_ratio"]
            cur["prologue_original_before_prologue_end"] = original_metrics["before_prologue_end"]
            cur["prologue_original_crosses_boundary"] = original_metrics["crosses_prologue_boundary"]
            cur["start"] = trimmed_start
            cur["end"] = trimmed_end

    start = float(cur.get("start", start) or start)
    end = float(cur.get("end", end) or end)
    cur.update(_build_prologue_metrics(start, end, prologue_end))
    cur["prologue_end"] = round(float(prologue_end), 3) if prologue_end is not None else None
    return cur


def _clip_range_before_story_end(
    start: float,
    end: float,
    story_end: float | None,
    *,
    min_duration: float = 0.5,
) -> tuple[float, float, bool]:
    safe_start = round(float(start or 0.0), 3)
    safe_end = round(float(end or safe_start), 3)
    if safe_end <= safe_start:
        safe_end = round(safe_start + min_duration, 3)
    if story_end is None or safe_end <= story_end or safe_start >= story_end - min_duration:
        return safe_start, safe_end, False

    trimmed_end = round(min(safe_end, story_end), 3)
    if trimmed_end <= safe_start + min_duration:
        return safe_start, safe_end, False
    return safe_start, trimmed_end, trimmed_end < safe_end


def _build_story_end_metrics(start: float, end: float, story_end: float | None) -> Dict[str, Any]:
    safe_start = round(float(start or 0.0), 3)
    safe_end = round(float(end or safe_start), 3)
    if safe_end <= safe_start:
        safe_end = round(safe_start + 0.5, 3)
    duration = max(safe_end - safe_start, 0.1)

    if story_end is None:
        return {
            "after_story_end": False,
            "crosses_story_end_boundary": False,
            "story_end_overlap_duration": 0.0,
            "story_end_overlap_ratio": 0.0,
        }

    overlap = max(0.0, safe_end - max(safe_start, story_end))
    return {
        "after_story_end": bool(safe_start >= story_end - 0.05),
        "crosses_story_end_boundary": bool(safe_start < story_end - 0.05 and safe_end > story_end + 0.05),
        "story_end_overlap_duration": round(overlap, 3),
        "story_end_overlap_ratio": round(min(overlap / duration, 1.0), 3),
    }


def _annotate_story_end_state(
    item: Dict[str, Any],
    story_end: float | None,
    *,
    trim_crossing: bool = False,
) -> Dict[str, Any]:
    cur = dict(item)
    start = float(cur.get("start", 0.0) or 0.0)
    end = float(cur.get("end", start) or start)
    original_metrics = _build_story_end_metrics(start, end, story_end)

    cur.setdefault("story_end_trimmed", False)
    if trim_crossing:
        trimmed_start, trimmed_end, trimmed = _clip_range_before_story_end(start, end, story_end)
        if trimmed:
            cur["story_end_trimmed"] = True
            cur["story_end_original_start"] = round(start, 3)
            cur["story_end_original_end"] = round(end, 3)
            cur["story_end_original_overlap_duration"] = original_metrics["story_end_overlap_duration"]
            cur["story_end_original_overlap_ratio"] = original_metrics["story_end_overlap_ratio"]
            cur["story_end_original_after_story_end"] = original_metrics["after_story_end"]
            cur["story_end_original_crosses_boundary"] = original_metrics["crosses_story_end_boundary"]
            cur["start"] = trimmed_start
            cur["end"] = trimmed_end

    start = float(cur.get("start", start) or start)
    end = float(cur.get("end", end) or end)
    cur.update(_build_story_end_metrics(start, end, story_end))
    cur["story_end"] = round(float(story_end), 3) if story_end is not None else None
    return cur


def _collect_highlight_ranges(range_items: List[Dict[str, Any]], prologue_end: float | None) -> List[Dict[str, Any]]:
    highlight_ranges = []
    for item in range_items or []:
        if not isinstance(item, dict):
            continue
        start = _parse_prompt_time(item.get("start"))
        end = _parse_prompt_time(item.get("end"))
        if start is None or end is None or end <= start:
            continue
        if prologue_end is not None:
            if end <= prologue_end + 0.5:
                continue
            if start < prologue_end:
                start = round(prologue_end, 3)
        highlight_ranges.append(
            {
                "start": start,
                "end": end,
                "reason": str(item.get("reason") or item.get("category") or "llm_highlight_window"),
                "category": str(item.get("category") or ""),
                "importance": str(item.get("importance") or "medium"),
                "raw_voice_priority": str(item.get("raw_voice_priority") or "low"),
            }
        )
    return highlight_ranges


def _clip_highlight_ranges_to_story_window(
    highlight_ranges: List[Dict[str, Any]],
    story_end: float | None,
) -> List[Dict[str, Any]]:
    if story_end is None:
        return list(highlight_ranges or [])

    clipped: List[Dict[str, Any]] = []
    for item in highlight_ranges or []:
        start = round(float(item.get("start", 0.0) or 0.0), 3)
        end = round(float(item.get("end", start) or start), 3)
        if start >= story_end - 0.05:
            continue
        end = round(min(end, story_end), 3)
        if end <= start:
            continue
        cur = dict(item)
        cur["start"] = start
        cur["end"] = end
        clipped.append(cur)
    return clipped


def _apply_full_subtitle_plan_to_chunks(
    plot_chunks: List[Dict[str, Any]],
    full_subtitle_understanding: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not plot_chunks:
        return []

    prologue_end = _parse_prompt_time(full_subtitle_understanding.get("prologue_end_time"))
    story_end = _parse_prompt_time(full_subtitle_understanding.get("story_end_time"))
    highlight_ranges = _collect_highlight_ranges(
        list(full_subtitle_understanding.get("highlight_windows") or []),
        prologue_end,
    )
    highlight_ranges = _clip_highlight_ranges_to_story_window(highlight_ranges, story_end)

    annotated: List[Dict[str, Any]] = []
    keep_indices = set()
    total = len(plot_chunks)
    for idx, chunk in enumerate(plot_chunks):
        cur = _annotate_prologue_state(chunk, prologue_end, trim_crossing=True)
        cur = _annotate_story_end_state(cur, story_end, trim_crossing=True)
        start = float(cur.get("start", 0.0) or 0.0)
        end = float(cur.get("end", start) or start)
        overlaps = [r for r in highlight_ranges if _ranges_overlap(start, end, r["start"], r["end"], 2.0)]
        cur["llm_window_selected"] = bool(overlaps)
        cur["llm_window_reasons"] = [r["reason"] for r in overlaps]
        cur["llm_window_categories"] = [r["category"] for r in overlaps if r["category"]]
        cur["llm_chunk_boost"] = 1.0 if overlaps else 0.0
        if cur.get("after_story_end"):
            cur["llm_window_selected"] = False
            cur["llm_window_reasons"] = ["suppressed_by_story_end_boundary"]
            cur["llm_window_categories"] = []
            cur["llm_chunk_boost"] = 0.0
        if overlaps:
            if any(r.get("raw_voice_priority") == "high" for r in overlaps):
                cur["raw_voice_retain_suggestion"] = True
            if any(r.get("importance") == "high" for r in overlaps):
                cur["importance_level"] = "high"
        annotated.append(cur)

    for idx, chunk in enumerate(annotated):
        importance = str(chunk.get("importance_level") or "medium")
        plot_role = str(chunk.get("plot_role") or "")
        if chunk.get("after_story_end"):
            continue
        keep = bool(chunk.get("llm_window_selected"))
        if not keep and not chunk.get("before_prologue_end") and importance == "high":
            keep = True
        if not keep and plot_role == "ending":
            keep = True
        if keep:
            keep_indices.add(idx)
            if idx > 0:
                prev = annotated[idx - 1]
                if not prev.get("after_story_end"):
                    keep_indices.add(idx - 1)
            if idx + 1 < total:
                nxt = annotated[idx + 1]
                if not nxt.get("after_story_end"):
                    keep_indices.add(idx + 1)

    filtered = []
    for idx, chunk in enumerate(annotated):
        if chunk.get("after_story_end"):
            continue
        if idx in keep_indices or not highlight_ranges:
            filtered.append(chunk)

    non_tail = [chunk for chunk in annotated if not chunk.get("after_story_end")]
    return filtered or non_tail or annotated


def _highlight_plan_windows(full_subtitle_understanding: Dict[str, Any], llm_highlight_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    windows: List[Dict[str, Any]] = []
    for source in (llm_highlight_plan or {}, full_subtitle_understanding or {}):
        for key in ("must_keep_ranges", "highlight_windows"):
            for raw in list(source.get(key) or []):
                if not isinstance(raw, dict):
                    continue
                normalized = _normalize_prompt_highlight_window(
                    raw,
                    default_reason=str(raw.get("reason") or key),
                    default_importance=str(raw.get("importance") or "medium"),
                    default_raw_voice_priority=str(raw.get("raw_voice_priority") or "low"),
                )
                if normalized:
                    windows.append(normalized)
    return windows


def _apply_llm_highlight_plan(
    scene_evidence: List[Dict[str, Any]],
    full_subtitle_understanding: Dict[str, Any],
    llm_highlight_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Annotate evidence with LLM/full-subtitle high-light signals without filtering it.

    Stage 3 typed selection still owns the final high-light decision. This layer
    only preserves signals from full-story understanding so they can boost typed
    selection and inform raw-voice retention.
    """
    selected_ids = {str(x).strip() for x in list((llm_highlight_plan or {}).get("selected_segment_ids") or []) if str(x or "").strip()}
    rejected_ids = {str(x).strip() for x in list((llm_highlight_plan or {}).get("rejected_segment_ids") or []) if str(x or "").strip()}
    raw_voice_ids = {str(x).strip() for x in list((llm_highlight_plan or {}).get("raw_voice_segment_ids") or []) if str(x or "").strip()}
    windows = _highlight_plan_windows(full_subtitle_understanding, llm_highlight_plan)
    parsed_windows = []
    for window in windows:
        window_start = _coerce_highlight_time(window.get("start"))
        window_end = _coerce_highlight_time(window.get("end"))
        if window_start is None or window_end is None or window_end <= window_start:
            continue
        parsed_windows.append((window, window_start, window_end))

    annotated: List[Dict[str, Any]] = []
    for item in scene_evidence or []:
        cur = dict(item)
        seg_id = str(cur.get("segment_id") or "").strip()
        scene_id = str(cur.get("scene_id") or "").strip()
        start = _coerce_highlight_time(cur.get("start"))
        if start is None:
            start = _coerce_highlight_time(cur.get("video_start"))
        if start is None:
            start = _coerce_highlight_time(cur.get("timestamp")) or 0.0
        end = _coerce_highlight_time(cur.get("end"), prefer_end=True)
        if end is None:
            end = _coerce_highlight_time(cur.get("video_end"), prefer_end=True)
        if end is None:
            end = _coerce_highlight_time(cur.get("timestamp"), prefer_end=True) or start
        id_hit = bool((seg_id and seg_id in selected_ids) or (scene_id and scene_id in selected_ids))
        reject_hit = bool((seg_id and seg_id in rejected_ids) or (scene_id and scene_id in rejected_ids))
        overlaps = [w for w, window_start, window_end in parsed_windows if _ranges_overlap(start, end, window_start, window_end, 1.0)]
        raw_voice_hit = bool((seg_id and seg_id in raw_voice_ids) or (scene_id and scene_id in raw_voice_ids))
        raw_voice_hit = raw_voice_hit or any(str(w.get("raw_voice_priority") or "").lower() == "high" for w in overlaps)

        cur["llm_highlight_selected"] = bool(id_hit or overlaps or cur.get("llm_window_selected"))
        cur["llm_highlight_rejected"] = bool(reject_hit and not cur["llm_highlight_selected"])
        cur["llm_highlight_reason"] = "segment_id" if id_hit else ("highlight_window" if overlaps else cur.get("llm_highlight_reason", ""))
        cur["llm_window_reasons"] = _unique_strings(list(cur.get("llm_window_reasons") or []) + [str(w.get("reason") or "highlight_window") for w in overlaps], limit=8)
        cur["llm_window_categories"] = _unique_strings(list(cur.get("llm_window_categories") or []) + [str(w.get("category") or "") for w in overlaps if w.get("category")], limit=8)
        if cur["llm_highlight_selected"]:
            cur["highlight_filter_selected"] = True
        if raw_voice_hit:
            cur["llm_raw_voice_keep"] = True
            cur["raw_voice_retain_suggestion"] = True
        annotated.append(cur)

    return annotated
