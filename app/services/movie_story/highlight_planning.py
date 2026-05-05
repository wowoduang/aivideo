from __future__ import annotations

"""Stage-B highlight planning contract for legacy narration migration.

This module does **not** call an LLM and does **not** write final narration.
It converts selected highlights + rich Stage-A evidence into the structured
planning layer that the legacy narration writer expects:

- why this highlight was selected
- what story role it plays in the final narration arc
- which evidence fields should be fed to narration_generation
- whether the narration-generation input contract is complete

The goal is to migrate the old project's story/highlight planning logic without
spending tokens while the migration is still being verified stage by stage.
"""

from typing import Any, Dict, List, Mapping, Sequence

JsonDict = Dict[str, Any]

STAGE_B_REQUIRED_HIGHLIGHT_FIELDS = [
    "highlight_id",
    "start",
    "end",
    "subtitle_text",
    "highlight_type",
    "story_role",
    "selection_reason",
    "score_breakdown",
    "source_scene_ids",
    "narration_intent",
    "_global_summary",
]

STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS = [
    "highlight_id",
    "time_window",
    "subtitle_text",
    "global_summary",
    "local_understanding",
    "story_function",
    "selection_reason",
    "narration_intent",
    "char_budget",
]


def _text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        text = "；".join(_text(x) for x in value if _text(x))
    elif isinstance(value, dict):
        text = "；".join(f"{k}:{_text(v)}" for k, v in value.items() if _text(v))
    else:
        text = str(value)
    text = text.strip()
    return text[:max_chars].rstrip() if max_chars and len(text) > max_chars else text


def _first_nonempty(*values: Any, max_chars: int = 0) -> str:
    for value in values:
        text = _text(value, max_chars=max_chars)
        if text:
            return text
    return ""


def _as_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, (tuple, set)):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _duration(item: Mapping[str, Any]) -> float:
    try:
        s = float(item.get("start", item.get("video_start", 0.0)) or 0.0)
        e = float(item.get("end", item.get("video_end", s)) or s)
        return max(0.2, e - s)
    except Exception:
        return 3.0


def estimate_zh_char_budget(duration: float, *, importance_level: str = "medium", highlight_type: str = "") -> int:
    """Conservative Chinese narration budget used only for contract validation."""
    # Mandarin TTS is often comfortable around 4-5 Chinese chars/sec for
    # commentary.  Keep a slightly higher cap for high-value highlights, but
    # this stage must not retime video boundaries.
    base = int(round(max(0.2, duration) * 4.6))
    if str(importance_level).lower() == "high":
        base += 10
    if any(k in str(highlight_type) for k in ["反转", "情绪", "冲突", "信息"]):
        base += 6
    return max(18, min(base, 90))


def _score_breakdown(item: Mapping[str, Any]) -> JsonDict:
    scores = item.get("scores") if isinstance(item.get("scores"), Mapping) else {}

    def f(*keys: str, default: float = 0.0) -> float:
        for key in keys:
            try:
                value = item.get(key, scores.get(key))
                if value not in (None, ""):
                    return round(float(value), 3)
            except Exception:
                continue
        return default

    story = f("story_score", "highlight_score", "score", default=0.0)
    info = f("information_score", default=0.0)
    emotion = f("emotion_score", default=0.0)
    character = f("character_score", default=0.0)
    visual = f("visual_score", default=0.0)
    audio = f("audio_score", default=0.0)
    # Stage-A enrichment may not have full sub-scores yet.  Derive sensible
    # signals from plot/highlight type so Stage-B can validate the contract.
    text = " ".join([
        _text(item.get("plot_function")),
        _text(item.get("highlight_type")),
        _text(item.get("story_function")),
        _text(item.get("narration_intent")),
    ])
    if story <= 0:
        story = 0.75 if text else 0.45
    if info <= 0 and any(k in text for k in ["信息", "揭露", "关键", "决定", "目标"]):
        info = 0.72
    if emotion <= 0 and any(k in text for k in ["情绪", "爆发", "冲突", "反转", "危机"]):
        emotion = 0.68
    if character <= 0 and any(k in text for k in ["人物", "动机", "关系", "选择"]):
        character = 0.62
    continuity = 0.75 if item.get("_global_summary") else 0.35
    return {
        "story": round(story, 3),
        "information": round(info, 3),
        "emotion": round(emotion, 3),
        "character": round(character, 3),
        "visual": round(visual, 3),
        "audio": round(audio, 3),
        "continuity": round(continuity, 3),
        "type_confidence": f("type_confidence", default=0.0),
        "overall": round(max(story, f("highlight_score", "score", default=story)), 3),
    }


def _story_role(item: Mapping[str, Any], idx: int, total: int) -> str:
    htype = _text(item.get("highlight_type"))
    plot = _text(item.get("plot_function"))
    story_fn = _text(item.get("story_function"))
    if idx == 1:
        return "开场钩子"
    if idx == total:
        return "阶段收束"
    joined = " ".join([htype, plot, story_fn])
    if any(k in joined for k in ["冲突", "危机", "对抗"]):
        return "主线冲突推进"
    if any(k in joined for k in ["信息", "揭露", "真相", "关键决定", "目标"]):
        return "关键信息揭露"
    if any(k in joined for k in ["反转", "突然", "变化"]):
        return "反转/局势变化"
    if any(k in joined for k in ["情绪", "人物", "关系"]):
        return "人物情绪与关系推进"
    return "剧情推进连接"


def _arc_position(role: str, idx: int, total: int) -> str:
    if idx == 1 or "开场" in role:
        return "opening_hook"
    if idx == total or "收束" in role:
        return "ending_resolution"
    if "冲突" in role:
        return "conflict_escalation"
    if "信息" in role:
        return "information_reveal"
    if "反转" in role:
        return "reversal"
    if "情绪" in role or "关系" in role:
        return "emotion_character"
    return "story_progression"


def _selection_reason(item: Mapping[str, Any], role: str) -> str:
    existing = _first_nonempty(item.get("selection_reason"), item.get("highlight_reason"), item.get("reason"), max_chars=260)
    if existing:
        return existing
    pieces = [
        f"承担{role}的作用",
        _text(item.get("real_narrative_state"), 160),
        _text(item.get("conflict_summary"), 140),
        _text(item.get("story_function"), 120),
    ]
    return "；".join([p for p in pieces if p])[:420] or "该片段承载剧情推进信息，适合进入高光解说。"


def _source_scene_ids(item: Mapping[str, Any]) -> List[str]:
    ids: List[str] = []
    for key in ("source_scene_ids", "scene_ids", "segment_ids", "evidence_ids"):
        for value in _as_list(item.get(key)):
            if value and value not in ids:
                ids.append(value)
    for key in ("scene_id", "segment_id", "candidate_id", "id"):
        value = _text(item.get(key))
        if value and value not in ids:
            ids.append(value)
    return ids


def build_narration_generation_input(item: Mapping[str, Any]) -> JsonDict:
    start = item.get("start", item.get("video_start"))
    end = item.get("end", item.get("video_end"))
    duration = _duration(item)
    importance = _text(item.get("importance_level")) or "medium"
    highlight_type = _first_nonempty(item.get("highlight_type"), item.get("plot_function"))
    char_budget = item.get("char_budget") or estimate_zh_char_budget(duration, importance_level=importance, highlight_type=highlight_type)
    return {
        "highlight_id": item.get("highlight_id"),
        "time_window": {"start": start, "end": end, "duration": round(duration, 3)},
        "subtitle_text": _text(item.get("subtitle_text"), 1200),
        "global_summary": item.get("_global_summary") or {},
        "local_understanding": item.get("local_understanding") or {},
        "story_function": item.get("story_function") or item.get("plot_function"),
        "selection_reason": item.get("selection_reason"),
        "narration_intent": item.get("narration_intent"),
        "char_budget": int(char_budget),
        "highlight_type": item.get("highlight_type"),
        "score_breakdown": item.get("score_breakdown") or {},
        "raw_voice_retain_suggestion": item.get("raw_voice_retain_suggestion", False),
        "stage_b_contract": "legacy_narration_generation_input",
    }


def score_stage_b_highlight(item: Mapping[str, Any]) -> JsonDict:
    missing_required: List[str] = []
    present_required: List[str] = []
    for key in STAGE_B_REQUIRED_HIGHLIGHT_FIELDS:
        value = item.get(key)
        ok = bool(value) and (not isinstance(value, (list, dict)) or len(value) > 0)
        (present_required if ok else missing_required).append(key)
    ni = item.get("narration_generation_input") if isinstance(item.get("narration_generation_input"), Mapping) else {}
    missing_input: List[str] = []
    present_input: List[str] = []
    for key in STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS:
        value = ni.get(key)
        ok = bool(value) and (not isinstance(value, (list, dict)) or len(value) > 0)
        (present_input if ok else missing_input).append(key)
    highlight_score = len(present_required) / max(1, len(STAGE_B_REQUIRED_HIGHLIGHT_FIELDS))
    input_score = len(present_input) / max(1, len(STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS))
    score = round(highlight_score * 0.55 + input_score * 0.45, 3)
    return {
        "score": score,
        "highlight_required_score": round(highlight_score, 3),
        "narration_input_score": round(input_score, 3),
        "missing_required": missing_required,
        "missing_narration_input": missing_input,
        "passed": highlight_score >= 0.9 and input_score >= 0.9,
    }


def enrich_selected_highlights_for_planning(
    highlights: Sequence[Mapping[str, Any]] | None,
    global_context: Mapping[str, Any] | None = None,
) -> List[JsonDict]:
    rows = [dict(x) for x in list(highlights or []) if isinstance(x, Mapping)]
    total = len(rows)
    out: List[JsonDict] = []
    for idx, src in enumerate(rows, start=1):
        item = dict(src)
        if global_context and not item.get("_global_summary"):
            item["_global_summary"] = dict(global_context)
        item["source_scene_ids"] = _source_scene_ids(item)
        item["highlight_type"] = _first_nonempty(item.get("highlight_type"), item.get("plot_function"), "剧情高光")
        item["highlight_type_key"] = _first_nonempty(item.get("highlight_type_key"), item.get("plot_function"), "story_highlight")
        role = _first_nonempty(item.get("story_role"), _story_role(item, idx, total))
        item["story_role"] = role
        item["highlight_arc_position"] = _arc_position(role, idx, total)
        item["selection_reason"] = _selection_reason(item, role)
        item["score_breakdown"] = _score_breakdown(item)
        item["char_budget"] = int(item.get("char_budget") or estimate_zh_char_budget(_duration(item), importance_level=_text(item.get("importance_level")) or "medium", highlight_type=item.get("highlight_type")))
        item["narration_generation_input"] = build_narration_generation_input(item)
        item["stage_b_quality"] = score_stage_b_highlight(item)
        out.append(item)
    return out


def evaluate_stage_b_highlights(items: Sequence[Mapping[str, Any]] | None, *, min_pass_rate: float = 0.9, min_type_count: int = 3, min_arc_count: int = 3) -> JsonDict:
    rows = list(items or [])
    scored = []
    type_set = set()
    arc_set = set()
    for index, item in enumerate(rows, start=1):
        q = item.get("stage_b_quality") if isinstance(item, Mapping) else None
        if not isinstance(q, Mapping):
            q = score_stage_b_highlight(item or {})
        if item.get("highlight_type"):
            type_set.add(str(item.get("highlight_type")))
        if item.get("highlight_arc_position"):
            arc_set.add(str(item.get("highlight_arc_position")))
        scored.append({
            "idx": index,
            "id": item.get("highlight_id") or item.get("scene_id") or item.get("segment_id") or item.get("id"),
            "score": q.get("score"),
            "passed": bool(q.get("passed")),
            "missing_required": q.get("missing_required") or [],
            "missing_narration_input": q.get("missing_narration_input") or [],
            "highlight_type": item.get("highlight_type"),
            "story_role": item.get("story_role"),
            "arc": item.get("highlight_arc_position"),
        })
    total = len(scored)
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    return {
        "stage": "stage_b_highlight_planning_contract",
        "total": total,
        "passed": passed,
        "failed": max(0, total - passed),
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        "type_count": len(type_set),
        "min_type_count": min_type_count,
        "arc_count": len(arc_set),
        "min_arc_count": min_arc_count,
        "overall_passed": bool(total and pass_rate >= min_pass_rate and len(type_set) >= min_type_count and len(arc_set) >= min_arc_count),
        "items": scored,
    }


__all__ = [
    "STAGE_B_REQUIRED_HIGHLIGHT_FIELDS",
    "STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS",
    "estimate_zh_char_budget",
    "build_narration_generation_input",
    "enrich_selected_highlights_for_planning",
    "score_stage_b_highlight",
    "evaluate_stage_b_highlights",
]
