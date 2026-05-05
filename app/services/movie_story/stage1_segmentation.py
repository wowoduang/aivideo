# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schemas import DraftStoryCandidate, SceneCandidate, SubtitleUnit


def parse_time(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).strip().replace(",", ".")
    try:
        parts = text.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except Exception:
        return None


def normalize_subtitle_segments(segments: Iterable[Dict[str, Any]]) -> List[SubtitleUnit]:
    units: List[SubtitleUnit] = []
    for i, seg in enumerate(segments or [], start=1):
        s = parse_time(seg.get("start") or seg.get("begin") or seg.get("from"))
        e = parse_time(seg.get("end") or seg.get("to") or seg.get("finish"))
        text = str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip()
        if (s is None or e is None) and seg.get("timestamp") and "-" in str(seg.get("timestamp")):
            left, right = str(seg.get("timestamp")).split("-", 1)
            s, e = parse_time(left), parse_time(right)
        if s is None or e is None:
            continue
        if e <= s:
            e = s + 0.3
        units.append(SubtitleUnit(f"sub_{i:05d}", round(s, 3), round(e, 3), text))
    units.sort(key=lambda x: (x.start, x.end))
    cleaned: List[SubtitleUnit] = []
    for u in units:
        if cleaned and u.text and cleaned[-1].text == u.text and u.start - cleaned[-1].end <= 0.8:
            cleaned[-1].end = max(cleaned[-1].end, u.end)
        else:
            cleaned.append(u)
    return cleaned


def detect_subtitle_boundaries(units: List[SubtitleUnit]) -> List[Dict[str, Any]]:
    out = []
    for a, b in zip(units, units[1:]):
        gap = b.start - a.end
        if gap >= 2.5:
            strength = "strong"
        elif gap >= 1.2:
            strength = "medium"
        elif gap >= 0.5 and re.search(r"[。！？!?]$", a.text or ""):
            strength = "weak"
        else:
            continue
        out.append({"time": round((a.end + b.start) / 2, 3), "strength": strength, "reason": ["subtitle_gap"], "gap": round(gap, 3)})
    return out


def normalize_boundaries(items: Iterable[Any], reason: str) -> List[Dict[str, Any]]:
    out = []
    for x in items or []:
        if isinstance(x, dict):
            t = parse_time(x.get("time") or x.get("timestamp") or x.get("start"))
            strength = str(x.get("strength") or "medium")
            reasons = list(x.get("reason") or x.get("reasons") or [reason])
        else:
            t, strength, reasons = parse_time(x), "medium", [reason]
        if t is not None:
            out.append({"time": round(t, 3), "strength": strength, "reason": reasons})
    return out


def fuse_boundaries(subtitle_boundaries, video_boundaries=None, audio_boundaries=None, *, story_start: float, story_end: float):
    raw = list(subtitle_boundaries or [])
    raw += normalize_boundaries(video_boundaries or [], "video_boundary")
    raw += normalize_boundaries(audio_boundaries or [], "audio_boundary")
    raw = [b for b in raw if story_start < float(b["time"]) < story_end]
    raw.sort(key=lambda b: b["time"])
    fused, cluster = [], []
    def flush():
        if not cluster:
            return
        reasons, score = [], 0
        for b in cluster:
            reasons += b.get("reason") or []
            score += {"weak": 1, "medium": 2, "strong": 3}.get(str(b.get("strength")), 2)
        fused.append({"time": round(sum(b["time"] for b in cluster) / len(cluster), 3),
                      "strength": "strong" if score >= 4 or len(cluster) >= 2 else "medium",
                      "reason": sorted(set(reasons))})
    for b in raw:
        if not cluster or abs(b["time"] - cluster[-1]["time"]) <= 1.0:
            cluster.append(b)
        else:
            flush(); cluster = [b]
    flush()
    return fused


def text_between(units: List[SubtitleUnit], start: float, end: float) -> Tuple[str, Optional[float], Optional[float]]:
    arr = [u for u in units if u.end > start and u.start < end]
    if not arr:
        return "", None, None
    return " ".join(u.text for u in arr if u.text).strip(), arr[0].start, arr[-1].end


def reasons_at(boundaries, t):
    rs = []
    for b in boundaries:
        if abs(float(b["time"]) - float(t)) <= 1.2:
            rs += b.get("reason") or []
    return sorted(set(rs)) or ["duration_limit"]


def build_scene_candidates(units, boundaries, *, story_start, story_end,
                           min_duration=8.0, target_max_duration=45.0, max_duration=75.0):
    cuts = sorted(set([round(story_start, 3)] + [b["time"] for b in boundaries] + [round(story_end, 3)]))
    ranges = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e <= s:
            continue
        if ranges and e - s < min_duration:
            ps, _, prs, _ = ranges.pop()
            ranges.append((ps, e, prs, reasons_at(boundaries, e)))
            continue
        if e - s > max_duration:
            cur = s
            while e - cur > max_duration:
                cut = cur + target_max_duration
                near = [b["time"] for b in boundaries if cur + 15 <= b["time"] <= cur + max_duration]
                if near:
                    cut = min(near, key=lambda x: abs(x - (cur + target_max_duration)))
                ranges.append((cur, cut, reasons_at(boundaries, cur), ["long_segment_split"]))
                cur = cut
            if e - cur >= min_duration:
                ranges.append((cur, e, ["long_segment_split"], reasons_at(boundaries, e)))
        else:
            ranges.append((s, e, reasons_at(boundaries, s), reasons_at(boundaries, e)))
    scenes = []
    for i, (s, e, rs, re) in enumerate(ranges, start=1):
        text, sub_s, sub_e = text_between(units, s, e)
        scenes.append(SceneCandidate(f"scene_{i:04d}", "scene", s, e, sub_s, sub_e, text, rs, re, "medium"))
    return scenes


def build_draft_story_candidates(scene_candidates: List[SceneCandidate], *, target_max_duration=120.0, max_duration=180.0):
    stories, buf = [], []
    def flush():
        nonlocal buf
        if not buf:
            return
        i = len(stories) + 1
        stories.append(DraftStoryCandidate(
            f"story_{i:04d}", "draft_story", buf[0].video_start, buf[-1].video_end,
            [x.candidate_id for x in buf], " ".join(x.subtitle_text for x in buf if x.subtitle_text).strip(),
            ["time_continuity", "scene_merge"] if len(buf) > 1 else ["single_scene"], "medium", True))
        buf = []
    for sc in scene_candidates:
        if not buf:
            buf.append(sc); continue
        duration = sc.video_end - buf[0].video_start
        gap = sc.video_start - buf[-1].video_end
        strong_break = "video_boundary" in sc.boundary_start_reason and gap >= 1.5
        if duration <= target_max_duration and not strong_break:
            buf.append(sc)
        elif duration <= max_duration and buf[-1].video_end - buf[0].video_start < 45:
            buf.append(sc)
        else:
            flush(); buf.append(sc)
    flush()
    return stories


def build_segmentation_candidates(video_path: str, subtitle_segments: List[Dict[str, Any]], *, segmentation_mode="hybrid",
                                  prologue_end=None, story_end=None, video_boundary_candidates=None, audio_boundaries=None):
    units = normalize_subtitle_segments(subtitle_segments)
    fallback_start = units[0].start if units else 0.0
    fallback_end = units[-1].end if units else 0.0
    start = float(prologue_end) if prologue_end is not None else fallback_start
    end = float(story_end) if story_end is not None else fallback_end
    if end <= start:
        start, end = fallback_start, fallback_end
    subtitle_b = detect_subtitle_boundaries(units)
    boundaries = fuse_boundaries(subtitle_b, video_boundary_candidates, audio_boundaries, story_start=start, story_end=end)
    scenes = build_scene_candidates(units, boundaries, story_start=start, story_end=end)
    stories = [] if segmentation_mode == "scene" else build_draft_story_candidates(scenes)
    coverage = {"policy": "stage1_cut_all_no_highlight_filter", "story_start": start, "story_end": end,
                "subtitle_units": len(units), "scene_count": len(scenes), "draft_story_count": len(stories),
                "fused_boundaries": len(boundaries), "scene_total_duration": round(sum(x.duration for x in scenes), 3),
                "draft_story_total_duration": round(sum(x.duration for x in stories), 3)}
    return scenes, stories, coverage
