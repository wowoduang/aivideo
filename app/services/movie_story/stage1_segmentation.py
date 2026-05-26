# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schemas import DraftStoryCandidate, SceneCandidate, SubtitleUnit, item_duration, to_dict

_END_PUNCT = re.compile(r"[。！？!?…]+[’'\")）】》]*$")
_NONSTORY_RULES = [
    ("intro", ["前情提要", "上集", "片头", "主题曲", "opening", "previously"]),
    ("outro", ["演职员", "片尾", "字幕组", "出品", "cast", "credits"]),
    ("preview", ["下集预告", "下集", "预告", "next episode"]),
    ("ad", ["广告", "赞助", "关注", "点赞", "subscribe"]),
]


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


def _subtitle_text(seg: Dict[str, Any]) -> str:
    return str(seg.get("text") or seg.get("content") or seg.get("subtitle") or seg.get("line") or "").strip()


def normalize_subtitle_segments(segments: Iterable[Dict[str, Any]]) -> List[SubtitleUnit]:
    """清洗字幕，但不根据剧情价值删除正文候选。"""
    units: List[SubtitleUnit] = []
    for i, seg in enumerate(segments or [], start=1):
        if not isinstance(seg, dict):
            continue
        s = parse_time(seg.get("start") or seg.get("begin") or seg.get("from"))
        e = parse_time(seg.get("end") or seg.get("to") or seg.get("finish"))
        text = _subtitle_text(seg)
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
        # 连续重复字幕合并，避免 ASR 重复导致候选切片膨胀。
        if cleaned and u.text and cleaned[-1].text == u.text and u.start - cleaned[-1].end <= 0.8:
            cleaned[-1].end = max(cleaned[-1].end, u.end)
            continue
        # 极短字幕并入前句；这属于字幕清洗，不属于高光筛选。
        if cleaned and u.duration < 0.35 and u.start - cleaned[-1].end <= 0.4:
            cleaned[-1].end = max(cleaned[-1].end, u.end)
            if u.text and u.text not in cleaned[-1].text:
                cleaned[-1].text = (cleaned[-1].text + " " + u.text).strip()
            continue
        cleaned.append(u)
    return cleaned


def detect_subtitle_boundaries(units: List[SubtitleUnit]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a, b in zip(units, units[1:]):
        gap = b.start - a.end
        strength = ""
        reasons: List[str] = []
        if gap >= 2.5:
            strength = "strong"; reasons.append("subtitle_gap_strong")
        elif gap >= 1.2:
            strength = "medium"; reasons.append("subtitle_gap")
        elif gap >= 0.5 and _END_PUNCT.search(a.text or ""):
            strength = "weak"; reasons.append("sentence_end_gap")
        if any(k in (b.text or "") for k in ["可是", "但是", "然而", "没想到", "突然", "随后", "另一边"]):
            strength = "medium" if not strength else strength
            reasons.append("topic_turning_word")
        if strength:
            out.append({"time": round((a.end + b.start) / 2, 3), "strength": strength, "reason": sorted(set(reasons)), "gap": round(gap, 3)})
    return out


def normalize_boundaries(items: Iterable[Any], reason: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for x in items or []:
        if isinstance(x, dict):
            t = parse_time(x.get("time") or x.get("timestamp") or x.get("start") or x.get("at"))
            strength = str(x.get("strength") or x.get("confidence") or "medium")
            reasons = list(x.get("reason") or x.get("reasons") or [reason])
        else:
            t, strength, reasons = parse_time(x), "medium", [reason]
        if t is not None:
            if strength not in {"weak", "medium", "strong"}:
                strength = "medium"
            out.append({"time": round(t, 3), "strength": strength, "reason": reasons})
    return out


def fuse_boundaries(subtitle_boundaries: Iterable[Dict[str, Any]], video_boundaries: Iterable[Any] | None = None,
                    audio_boundaries: Iterable[Any] | None = None, *, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    raw = list(subtitle_boundaries or [])
    raw += normalize_boundaries(video_boundaries or [], "video_boundary")
    raw += normalize_boundaries(audio_boundaries or [], "audio_boundary")
    raw = [b for b in raw if story_start < float(b["time"]) < story_end]
    raw.sort(key=lambda b: b["time"])
    fused: List[Dict[str, Any]] = []
    cluster: List[Dict[str, Any]] = []

    def flush() -> None:
        nonlocal cluster
        if not cluster:
            return
        reasons: List[str] = []
        score = 0
        for b in cluster:
            reasons += list(b.get("reason") or [])
            score += {"weak": 1, "medium": 2, "strong": 3}.get(str(b.get("strength")), 2)
        fused.append({
            "time": round(sum(float(b["time"]) for b in cluster) / len(cluster), 3),
            "strength": "strong" if score >= 4 or len(cluster) >= 2 else "medium",
            "reason": sorted(set(reasons)),
        })
        cluster = []

    for b in raw:
        if not cluster or abs(float(b["time"]) - float(cluster[-1]["time"])) <= 1.0:
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


def _detect_nonstory_tag(text: str, start: float, end: float, story_start: float, story_end: float) -> Optional[str]:
    lower = (text or "").lower()
    for tag, keys in _NONSTORY_RULES:
        if any(k.lower() in lower for k in keys):
            return tag
    if end <= story_start + 60 and len(text) < 8:
        return "intro"
    if start >= story_end - 90 and any(k in lower for k in ["cast", "credits", "字幕", "出品"]):
        return "outro"
    return None


def _reasons_at(boundaries: List[Dict[str, Any]], t: float, default: str) -> List[str]:
    rs: List[str] = []
    for b in boundaries:
        if abs(float(b["time"]) - float(t)) <= 1.2:
            rs += list(b.get("reason") or [])
    return sorted(set(rs)) or [default]


def build_scene_candidates(units: List[SubtitleUnit], boundaries: List[Dict[str, Any]], *, story_start: float, story_end: float,
                           min_duration: float = 8.0, target_max_duration: float = 45.0, max_duration: float = 75.0) -> List[SceneCandidate]:
    cuts = sorted(set([round(story_start, 3)] + [float(b["time"]) for b in boundaries] + [round(story_end, 3)]))
    ranges: List[Tuple[float, float, List[str], List[str], str]] = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e <= s:
            continue
        start_reasons = _reasons_at(boundaries, s, "story_start" if i == 0 else "duration_limit")
        end_reasons = _reasons_at(boundaries, e, "story_end" if i == len(cuts) - 2 else "duration_limit")
        if ranges and e - s < min_duration:
            ps, _, prs, _, _ = ranges.pop()
            ranges.append((ps, e, prs, end_reasons, "medium"))
            continue
        if e - s > max_duration:
            cur = s
            while e - cur > max_duration:
                near = [float(b["time"]) for b in boundaries if cur + 15 <= float(b["time"]) <= cur + max_duration]
                cut = min(near, key=lambda x: abs(x - (cur + target_max_duration))) if near else cur + target_max_duration
                ranges.append((cur, cut, _reasons_at(boundaries, cur, "long_segment_split"), ["long_segment_split"], "low"))
                cur = cut
            if e - cur >= min_duration:
                ranges.append((cur, e, ["long_segment_split"], end_reasons, "medium"))
        else:
            ranges.append((s, e, start_reasons, end_reasons, "high" if "subtitle_gap_strong" in end_reasons else "medium"))

    scenes: List[SceneCandidate] = []
    for i, (s, e, rs, re, confidence) in enumerate(ranges, start=1):
        text, sub_s, sub_e = text_between(units, s, e)
        tag = _detect_nonstory_tag(text, s, e, story_start, story_end)
        ctype = "silent_action_candidate" if not text else "scene"
        scenes.append(SceneCandidate(
            candidate_id=f"scene_{i:04d}",
            candidate_type=ctype,
            video_start=round(s, 3),
            video_end=round(e, 3),
            subtitle_start=sub_s,
            subtitle_end=sub_e,
            subtitle_text=text,
            boundary_start_reason=rs,
            boundary_end_reason=re,
            boundary_confidence=confidence,
            source_scene_ids=[],
            nonstory_tag=tag,
            need_semantic_review=True,
        ))
    return scenes


def _should_break_story(prev: SceneCandidate, cur: SceneCandidate) -> bool:
    gap = cur.video_start - prev.video_end
    if gap >= 3.0:
        return True
    strong_visual = "video_boundary" in cur.boundary_start_reason and gap >= 1.0
    nonstory_changed = prev.nonstory_tag != cur.nonstory_tag and (prev.nonstory_tag or cur.nonstory_tag)
    return bool(strong_visual or nonstory_changed)


def build_draft_story_candidates(scene_candidates: List[SceneCandidate], *, target_max_duration: float = 120.0,
                                 max_duration: float = 180.0) -> List[DraftStoryCandidate]:
    stories: List[DraftStoryCandidate] = []
    buf: List[SceneCandidate] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        i = len(stories) + 1
        nonstory = buf[0].nonstory_tag if all(x.nonstory_tag == buf[0].nonstory_tag for x in buf) else None
        stories.append(DraftStoryCandidate(
            candidate_id=f"story_{i:04d}",
            candidate_type="draft_story",
            video_start=buf[0].video_start,
            video_end=buf[-1].video_end,
            children=[x.candidate_id for x in buf],
            subtitle_text=" ".join(x.subtitle_text for x in buf if x.subtitle_text).strip(),
            merge_reason=["time_continuity", "scene_merge"] if len(buf) > 1 else ["single_scene"],
            boundary_confidence="low" if any(x.boundary_confidence == "low" for x in buf) else "medium",
            need_semantic_review=True,
            nonstory_tag=nonstory,
        ))
        buf = []

    for sc in scene_candidates:
        if not buf:
            buf.append(sc); continue
        duration = sc.video_end - buf[0].video_start
        if duration <= target_max_duration and not _should_break_story(buf[-1], sc):
            buf.append(sc)
        elif duration <= max_duration and (buf[-1].video_end - buf[0].video_start) < 45 and not _should_break_story(buf[-1], sc):
            buf.append(sc)
        else:
            flush(); buf.append(sc)
    flush()
    return stories


def _coverage_report(scene_candidates: List[SceneCandidate], story_start: float, story_end: float, boundaries: List[Dict[str, Any]], units: List[SubtitleUnit]) -> Dict[str, Any]:
    gaps: List[Dict[str, float]] = []
    cursor = story_start
    for sc in scene_candidates:
        if sc.video_start > cursor + 0.75:
            gaps.append({"start": round(cursor, 3), "end": round(sc.video_start, 3), "duration": round(sc.video_start - cursor, 3)})
        cursor = max(cursor, sc.video_end)
    if story_end > cursor + 0.75:
        gaps.append({"start": round(cursor, 3), "end": round(story_end, 3), "duration": round(story_end - cursor, 3)})
    total = round(max(0.0, story_end - story_start), 3)
    covered = round(sum(item_duration(x) for x in scene_candidates), 3)
    return {
        "policy": "stage1_cut_all_no_highlight_filter",
        "forbidden_inputs": ["target_minutes", "highlight_selectivity", "final_story_score", "tts_duration"],
        "story_start": round(story_start, 3),
        "story_end": round(story_end, 3),
        "story_duration": total,
        "subtitle_units": len(units),
        "fused_boundaries": len(boundaries),
        "scene_count": len(scene_candidates),
        "scene_total_duration": covered,
        "coverage_ratio": round(covered / total, 4) if total > 0 else 0.0,
        "large_gaps": [g for g in gaps if g["duration"] >= 2.0],
        "nonstory_tag_counts": {tag: sum(1 for x in scene_candidates if x.nonstory_tag == tag) for tag in sorted({x.nonstory_tag for x in scene_candidates if x.nonstory_tag})},
    }


def build_segmentation_candidates(video_path: str, subtitle_segments: List[Dict[str, Any]], *, segmentation_mode: str = "hybrid",
                                  prologue_end: float | None = None, story_end: float | None = None,
                                  video_boundary_candidates: Optional[List[Any]] = None,
                                  audio_boundaries: Optional[List[Any]] = None) -> Tuple[List[SceneCandidate], List[DraftStoryCandidate], Dict[str, Any]]:
    units = normalize_subtitle_segments(subtitle_segments)
    fallback_start = units[0].start if units else 0.0
    fallback_end = units[-1].end if units else (float(story_end) if story_end is not None else fallback_start)
    start = float(prologue_end) if prologue_end is not None else fallback_start
    end = float(story_end) if story_end is not None else fallback_end
    if end <= start:
        start, end = fallback_start, fallback_end
    subtitle_b = detect_subtitle_boundaries(units)
    boundaries = fuse_boundaries(subtitle_b, video_boundary_candidates, audio_boundaries, story_start=start, story_end=end)
    scenes = build_scene_candidates(units, boundaries, story_start=start, story_end=end) if end > start else []
    stories: List[DraftStoryCandidate] = []
    if segmentation_mode in {"story", "hybrid", "draft_story"}:
        stories = build_draft_story_candidates(scenes)
    coverage = _coverage_report(scenes, start, end, boundaries, units)
    coverage["draft_story_count"] = len(stories)
    coverage["draft_story_total_duration"] = round(sum(item_duration(x) for x in stories), 3)
    coverage["video_path"] = video_path
    coverage["segmentation_mode"] = segmentation_mode
    return scenes, stories, coverage
