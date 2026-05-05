# -*- coding: utf-8 -*-
"""Typed highlight candidate building and selection.

Pure module: no file I/O, no config access, no LLM calls.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.services.movie_story.highlight_typing import TYPE_CONFIGS, classify_scene, parse_type_quotas, safe_float

Record = Dict[str, Any]


def _time_pair(item: Mapping[str, Any]) -> Tuple[float, float]:
    start = item.get("video_start", item.get("start", item.get("semantic_start", item.get("source_start", 0.0))))
    end = item.get("video_end", item.get("end", item.get("semantic_end", item.get("source_end", 0.0))))
    s, e = safe_float(start), safe_float(end)
    if e <= s:
        e = s + max(safe_float(item.get("duration"), 1.0), 1.0)
    return s, e


def _time_key(item: Mapping[str, Any]) -> Tuple[float, float, str]:
    s, e = _time_pair(item)
    return (s, e, _record_id(item))


def _record_id(item: Mapping[str, Any]) -> str:
    return str(item.get("scene_id") or item.get("segment_id") or item.get("candidate_id") or item.get("id") or item.get("highlight_id") or "")


def sort_chronological(records: Sequence[Mapping[str, Any]]) -> List[Record]:
    """Sort selected/candidate records by movie time for narration and output."""
    out: List[Record] = [dict(x) for x in (records or []) if isinstance(x, Mapping)]
    out.sort(key=_time_key)
    for idx, item in enumerate(out, start=1):
        item["movie_order"] = idx
        item["narration_order"] = idx
        item.setdefault("timeline_order", idx)
    return out


def _scene_in_story(scene: Mapping[str, Any], story: Mapping[str, Any]) -> bool:
    ss, se = _time_pair(scene)
    ts, te = _time_pair(story)
    if te <= ts:
        return False
    center = (ss + se) / 2.0
    return ts <= center <= te or (ss >= ts and se <= te)


def _story_text(story: Mapping[str, Any]) -> str:
    for key in ("story_text", "text", "subtitle_text", "summary", "content"):
        value = story.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_typed_candidates(
    scenes: Sequence[Mapping[str, Any]],
    stories: Sequence[Mapping[str, Any]],
    *,
    min_confidence: float = 0.52,
    fallback_confidence: float = 0.45,
) -> List[Record]:
    story_ranges = []
    for i, story in enumerate(stories, start=1):
        s, e = _time_pair(story)
        sid = str(story.get("story_id") or story.get("candidate_id") or story.get("id") or f"story_{i:04d}")
        story_ranges.append((sid, s, e, story))
    out: List[Record] = []
    for scene in scenes:
        ss, se = _time_pair(scene)
        parent = None
        for info in story_ranges:
            if _scene_in_story(scene, info[3]):
                parent = info
                break
        if parent is None:
            parent = ("story_unassigned", ss, se, {})
        sid, st, ed, story = parent
        for label in classify_scene(scene, min_confidence=min_confidence, fallback_confidence=fallback_confidence):
            item = dict(scene)
            item.update({
                "candidate_type": "typed_highlight_candidate",
                "scene_id": _record_id(scene),
                "parent_story_id": sid,
                "parent_story_start": st,
                "parent_story_end": ed,
                "parent_story_text": _story_text(story),
                "highlight_type_key": label["highlight_type_key"],
                "highlight_type": label["highlight_type"],
                "highlight_types": [label["highlight_type"]],
                "highlight_type_keys": [label["highlight_type_key"]],
                "type_confidence": label["type_confidence"],
                "type_evidence": label.get("type_evidence") or [],
                "matched_keywords": label.get("matched_keywords") or [],
                "evidence_text": label.get("evidence_text") or "",
                "narration_hint": label.get("narration_hint") or "",
                "type_selected": bool(label.get("selected")),
                "selected": False,
                "drop_reason": "pending_type_pool_selection",
            })
            out.append(item)
    return out


def _rank(item: Mapping[str, Any]) -> Tuple[float, float, float, float]:
    return (
        safe_float(item.get("type_confidence")),
        safe_float(item.get("highlight_score", item.get("score", 0.0))),
        safe_float(item.get("story_score")),
        safe_float(item.get("emotion_score")),
    )


def select_by_type_pools(
    candidates: Sequence[Mapping[str, Any]],
    *,
    quotas: Optional[Mapping[str, int]] = None,
    min_confidence: float = 0.52,
    fallback_confidence: float = 0.45,
    min_base_score: float = 0.18,
    target_items: int = 45,
) -> Tuple[List[Record], Record]:
    quotas = dict(quotas or {cfg["key"]: int(cfg.get("quota", 5)) for cfg in TYPE_CONFIGS})
    pools: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for item in candidates:
        pools[str(item.get("highlight_type_key") or "")].append(item)
    selected_pairs: set[Tuple[str, str]] = set()
    selected: List[Record] = []
    audited: List[Record] = []
    for cfg in TYPE_CONFIGS:
        key = cfg["key"]
        quota = int(quotas.get(key, cfg.get("quota", 5)))
        kept = 0
        for src in sorted(pools.get(key, []), key=_rank, reverse=True):
            rec = dict(src)
            pair = (str(rec.get("parent_story_id") or ""), key)
            base_score = safe_float(rec.get("highlight_score", rec.get("score", 0.0)))
            conf = safe_float(rec.get("type_confidence"))
            if kept >= quota:
                rec.update(selected=False, drop_reason=f"type_quota_full:{key}")
            elif conf < min_confidence:
                rec.update(selected=False, drop_reason=f"type_confidence_below_{min_confidence}")
            elif base_score < min_base_score:
                rec.update(selected=False, drop_reason=f"base_score_below_{min_base_score}")
            elif pair in selected_pairs:
                rec.update(selected=False, drop_reason="same_story_same_type_already_selected")
            else:
                rec.update(selected=True, drop_reason="")
                selected_pairs.add(pair)
                selected.append(rec)
                kept += 1
            audited.append(rec)
    if len(selected) < target_items:
        for src in sorted(candidates, key=_rank, reverse=True):
            if len(selected) >= target_items:
                break
            key = str(src.get("highlight_type_key") or "")
            pair = (str(src.get("parent_story_id") or ""), key)
            if pair in selected_pairs:
                continue
            if safe_float(src.get("type_confidence")) < fallback_confidence:
                continue
            if safe_float(src.get("highlight_score", src.get("score", 0.0))) < min_base_score:
                continue
            rec = dict(src)
            rec.update(selected=True, drop_reason="recall_fill_by_type_pool")
            selected_pairs.add(pair)
            selected.append(rec)
            audited.append(rec)
    return audited, {
        "policy": "typed_highlight_pools",
        "duration_cap": None,
        "min_gap_seconds": None,
        "target_items": target_items,
        "type_quotas": dict(quotas),
        "type_pool_counts": {k: len(v) for k, v in pools.items()},
        "selected_type_distribution": type_distribution(selected),
    }


def merge_selected_records(records: Sequence[Mapping[str, Any]]) -> List[Record]:
    grouped: Dict[str, Record] = {}
    for item in records:
        if not item.get("selected"):
            continue
        key = _record_id(item) or f"scene_{len(grouped)+1:04d}"
        if key not in grouped:
            base = dict(item)
            base["type_details"] = []
            base["highlight_types"] = []
            base["highlight_type_keys"] = []
            grouped[key] = base
        tgt = grouped[key]
        label = str(item.get("highlight_type") or "")
        type_key = str(item.get("highlight_type_key") or "")
        if label and label not in tgt["highlight_types"]:
            tgt["highlight_types"].append(label)
        if type_key and type_key not in tgt["highlight_type_keys"]:
            tgt["highlight_type_keys"].append(type_key)
        tgt["type_details"].append({
            "highlight_type_key": type_key,
            "highlight_type": label,
            "type_confidence": item.get("type_confidence"),
            "type_evidence": item.get("type_evidence") or [],
            "matched_keywords": item.get("matched_keywords") or [],
            "evidence_text": item.get("evidence_text") or "",
            "narration_hint": item.get("narration_hint") or "",
            "drop_reason": item.get("drop_reason") or "",
        })
    result = list(grouped.values())
    for item in result:
        details = sorted(item.get("type_details") or [], key=lambda x: safe_float(x.get("type_confidence")), reverse=True)
        item["type_details"] = details
        if details:
            item["highlight_type"] = details[0].get("highlight_type")
            item["highlight_type_key"] = details[0].get("highlight_type_key")
            item["type_confidence"] = details[0].get("type_confidence")
            item["evidence_text"] = details[0].get("evidence_text")
            item["narration_hint"] = "；".join([d.get("narration_hint", "") for d in details if d.get("narration_hint")])
    result.sort(key=_rank, reverse=True)
    for idx, item in enumerate(result, start=1):
        item["selection_rank"] = idx
    return result


def type_distribution(records: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = defaultdict(int)
    for item in records:
        labels = item.get("highlight_types") or [item.get("highlight_type")]
        for label in labels:
            if label:
                dist[str(label)] += 1
    return dict(dist)


__all__ = [
    "parse_type_quotas",
    "sort_chronological",
    "build_typed_candidates",
    "select_by_type_pools",
    "merge_selected_records",
    "type_distribution",
]
