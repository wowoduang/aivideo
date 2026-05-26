from __future__ import annotations

"""Stage-C legacy narration_generation input replay contract.

Stage C still does **not** call an LLM and does **not** evaluate final
narration wording.  Its job is to prove that the new pipeline can build the
same kind of prompt input package that the old project's
movie_story_narration/narration_generation writer consumed.

This prevents wasting tokens before the global/local/highlight evidence chain
is ready.  The output is an audit-only replay package that is JSON-serializable,
budgeted, and explicitly marked as LLM disabled.
"""

import json
from typing import Any, Dict, List, Mapping, Sequence

JsonDict = Dict[str, Any]

STAGE_C_STAGE_NAME = "06b_narration_generation_input_contract"
STAGE_C_PROMPT_NAMESPACE = "movie_story_narration"
STAGE_C_PROMPT_NAME = "narration_generation"

STAGE_C_REQUIRED_ITEM_FIELDS = [
    "highlight_id",
    "prompt_namespace",
    "prompt_name",
    "llm_call_enabled",
    "legacy_prompt_payload",
    "segment_json",
    "project_context",
    "style",
    "char_budget",
    "input_contract_quality",
]

STAGE_C_REQUIRED_PAYLOAD_FIELDS = [
    "segment_json",
    "project_context",
    "style",
    "char_budget",
    "global_summary",
    "local_understanding",
    "story_function",
    "selection_reason",
    "narration_intent",
]

STAGE_C_REQUIRED_SEGMENT_FIELDS = [
    "highlight_id",
    "timestamp",
    "start",
    "end",
    "subtitle_text",
    "surface_dialogue_meaning",
    "real_narrative_state",
    "conflict_summary",
    "character_motivation",
    "story_function",
    "plot_function",
    "importance_level",
    "narration_intent",
    "selection_reason",
    "_global_summary",
]


def _text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (list, tuple, set)):
        text = "；".join(_text(x) for x in value if _text(x))
    elif isinstance(value, Mapping):
        text = "；".join(f"{k}:{_text(v)}" for k, v in value.items() if _text(v))
    else:
        text = str(value).strip()
    return text[:max_chars].rstrip() if max_chars and len(text) > max_chars else text


def _first_nonempty(*values: Any, max_chars: int = 0) -> str:
    for value in values:
        text = _text(value, max_chars=max_chars)
        if text:
            return text
    return ""


def _as_dict(value: Any) -> JsonDict:
    return dict(value) if isinstance(value, Mapping) else {}


def _duration(item: Mapping[str, Any]) -> float:
    try:
        s = float(item.get("start", item.get("video_start", 0.0)) or 0.0)
        e = float(item.get("end", item.get("video_end", s)) or s)
        return round(max(0.001, e - s), 3)
    except Exception:
        return 3.0


def _timestamp(item: Mapping[str, Any]) -> str:
    existing = _text(item.get("timestamp"))
    if existing:
        return existing
    try:
        s = float(item.get("start", item.get("video_start", 0.0)) or 0.0)
        e = float(item.get("end", item.get("video_end", s)) or s)
        return f"{s:.3f}-{e:.3f}"
    except Exception:
        return ""


def _json_clone(value: Any) -> Any:
    """Make payload audit-safe by forcing JSON serializability."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def build_legacy_segment_json(item: Mapping[str, Any]) -> JsonDict:
    local = _as_dict(item.get("local_understanding"))
    global_summary = _as_dict(item.get("_global_summary") or item.get("global_summary"))
    start = item.get("start", item.get("video_start"))
    end = item.get("end", item.get("video_end"))
    return _json_clone({
        "highlight_id": item.get("highlight_id") or item.get("id") or item.get("candidate_id"),
        "segment_id": item.get("segment_id") or item.get("scene_id") or item.get("candidate_id"),
        "scene_id": item.get("scene_id"),
        "timestamp": _timestamp(item),
        "start": start,
        "end": end,
        "duration": _duration(item),
        "subtitle_text": _first_nonempty(item.get("subtitle_text"), item.get("main_text_evidence"), item.get("text"), max_chars=1600),
        "main_text_evidence": _first_nonempty(item.get("main_text_evidence"), item.get("subtitle_text"), max_chars=1600),
        "surface_dialogue_meaning": _first_nonempty(item.get("surface_dialogue_meaning"), local.get("surface_dialogue_meaning"), max_chars=500),
        "real_narrative_state": _first_nonempty(item.get("real_narrative_state"), local.get("real_narrative_state"), max_chars=700),
        "conflict_summary": _first_nonempty(item.get("conflict_summary"), local.get("conflict_summary"), max_chars=600),
        "character_motivation": _first_nonempty(item.get("character_motivation"), local.get("character_motivation"), max_chars=600),
        "story_function": _first_nonempty(item.get("story_function"), item.get("plot_function"), local.get("story_function"), max_chars=300),
        "plot_function": _first_nonempty(item.get("plot_function"), item.get("highlight_type"), max_chars=120),
        "importance_level": _first_nonempty(item.get("importance_level"), "medium"),
        "emotion_hint": _first_nonempty(item.get("emotion_hint"), item.get("emotion"), max_chars=120),
        "narration_intent": _first_nonempty(item.get("narration_intent"), local.get("narration_intent"), max_chars=700),
        "selection_reason": _first_nonempty(item.get("selection_reason"), item.get("highlight_reason"), max_chars=700),
        "highlight_type": _first_nonempty(item.get("highlight_type"), item.get("plot_function"), max_chars=120),
        "story_role": _first_nonempty(item.get("story_role"), max_chars=160),
        "score_breakdown": _as_dict(item.get("score_breakdown")),
        "local_understanding": local,
        "story_validation": _as_dict(item.get("story_validation")),
        "visual_summary": item.get("visual_summary") or [],
        "representative_frames": item.get("representative_frames") or [],
        "speaker_names": item.get("speaker_names") or [],
        "speaker_attribution_confidence": item.get("speaker_attribution_confidence") or "unknown",
        "raw_voice_retain_suggestion": item.get("raw_voice_retain_suggestion"),
        "_global_summary": global_summary,
    })


def build_project_context(global_summary: Mapping[str, Any] | None, *, video_title: str = "", style: str = "short_drama") -> JsonDict:
    gs = _as_dict(global_summary)
    return _json_clone({
        "video_title": _first_nonempty(video_title, gs.get("video_title")),
        "style": style,
        "genre": gs.get("genre") or "剧情解说",
        "main_conflict": gs.get("main_conflict") or "",
        "story_theme": gs.get("story_theme") or "",
        "main_characters": gs.get("main_characters") or [],
        "timeline_summary": gs.get("timeline_summary") or [],
        "relationship_map": gs.get("relationship_map") or [],
        "risk_flags": gs.get("risk_flags") or [],
        "migration_stage": "stage_c_narration_generation_input_replay",
    })


def _char_budget(item: Mapping[str, Any]) -> int:
    try:
        value = item.get("char_budget") or _as_dict(item.get("narration_generation_input")).get("char_budget")
        if value:
            return int(value)
    except Exception as _e:
        logger.debug("char_budget 解析失败，使用时长估算 fallback: {}", _e)
    # Conservative fallback: this is only for prompt-input contract validation.
    return max(18, min(int(round(_duration(item) * 4.6)) + 8, 90))


def build_narration_generation_replay_item(
    item: Mapping[str, Any],
    *,
    global_summary: Mapping[str, Any] | None = None,
    style: str = "short_drama",
    video_title: str = "",
    max_input_chars: int = 12000,
) -> JsonDict:
    gs = _as_dict(global_summary) or _as_dict(item.get("_global_summary")) or _as_dict(_as_dict(item.get("narration_generation_input")).get("global_summary"))
    segment_json = build_legacy_segment_json({**dict(item), "_global_summary": gs})
    project_context = build_project_context(gs, video_title=video_title, style=style)
    char_budget = _char_budget(item)
    payload = {
        "segment_json": segment_json,
        "project_context": project_context,
        "style": style,
        "style_description": "短剧/影视解说风格：讲剧情功能、人物动机和冲突推进，不逐句复述台词。",
        "style_examples": [],
        "char_budget": char_budget,
        "global_summary": gs,
        "local_understanding": segment_json.get("local_understanding") or {},
        "story_function": segment_json.get("story_function"),
        "selection_reason": segment_json.get("selection_reason"),
        "narration_intent": segment_json.get("narration_intent"),
        "raw_voice_keep_hint": segment_json.get("raw_voice_retain_suggestion"),
    }
    payload = _json_clone(payload)
    payload_chars = len(json.dumps(payload, ensure_ascii=False, default=str))
    item_id = segment_json.get("highlight_id") or item.get("highlight_id") or item.get("id")
    replay = {
        "candidate_id": item_id,
        "highlight_id": item_id,
        "candidate_type": "stage_c_narration_generation_input_contract",
        "start": segment_json.get("start"),
        "end": segment_json.get("end"),
        "video_start": segment_json.get("start"),
        "video_end": segment_json.get("end"),
        "timestamp": segment_json.get("timestamp"),
        "subtitle_text": segment_json.get("subtitle_text"),
        "text": segment_json.get("narration_intent") or segment_json.get("real_narrative_state") or segment_json.get("subtitle_text"),
        "prompt_namespace": STAGE_C_PROMPT_NAMESPACE,
        "prompt_name": STAGE_C_PROMPT_NAME,
        "llm_call_enabled": False,
        "llm_disabled_reason": "stage_c_input_replay_only_no_token_spend",
        "legacy_prompt_payload": payload,
        "segment_json": segment_json,
        "project_context": project_context,
        "style": style,
        "char_budget": char_budget,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": payload_chars <= max_input_chars,
        "input_contract_quality": {"status": "pending"},
    }
    replay["input_contract_quality"] = score_stage_c_item(replay, max_input_chars=max_input_chars)
    return replay


def build_stage_c_replay_items(
    planned_highlights: Sequence[Mapping[str, Any]],
    global_summary: Mapping[str, Any] | None = None,
    *,
    style: str = "short_drama",
    video_title: str = "",
    max_input_chars: int = 12000,
) -> List[JsonDict]:
    return [
        build_narration_generation_replay_item(
            item,
            global_summary=global_summary,
            style=style,
            video_title=video_title,
            max_input_chars=max_input_chars,
        )
        for item in (planned_highlights or [])
        if isinstance(item, Mapping)
    ]


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def score_stage_c_item(item: Mapping[str, Any], *, max_input_chars: int = 12000) -> JsonDict:
    missing_item: List[str] = []
    for key in STAGE_C_REQUIRED_ITEM_FIELDS:
        if not _has_value(item.get(key)) and key != "llm_call_enabled":
            missing_item.append(key)
    # llm_call_enabled is required and must be exactly False in Stage C.
    if item.get("llm_call_enabled") is not False:
        missing_item.append("llm_call_enabled_false")

    payload = _as_dict(item.get("legacy_prompt_payload"))
    missing_payload = [key for key in STAGE_C_REQUIRED_PAYLOAD_FIELDS if not _has_value(payload.get(key))]
    segment = _as_dict(item.get("segment_json") or payload.get("segment_json"))
    missing_segment = [key for key in STAGE_C_REQUIRED_SEGMENT_FIELDS if not _has_value(segment.get(key))]

    try:
        payload_chars = int(item.get("payload_chars") or len(json.dumps(payload, ensure_ascii=False, default=str)))
    except Exception:
        payload_chars = max_input_chars + 1
    budget_ok = payload_chars <= max_input_chars

    item_score = 1.0 - (len(missing_item) / max(1, len(STAGE_C_REQUIRED_ITEM_FIELDS)))
    payload_score = 1.0 - (len(missing_payload) / max(1, len(STAGE_C_REQUIRED_PAYLOAD_FIELDS)))
    segment_score = 1.0 - (len(missing_segment) / max(1, len(STAGE_C_REQUIRED_SEGMENT_FIELDS)))
    score = round(max(0.0, item_score * 0.25 + payload_score * 0.35 + segment_score * 0.3 + (0.1 if budget_ok else 0.0)), 3)
    passed = score >= 0.9 and not missing_item and not missing_payload and len(missing_segment) <= 1 and budget_ok and item.get("llm_call_enabled") is False
    return {
        "score": score,
        "passed": passed,
        "missing_item_fields": missing_item,
        "missing_payload_fields": missing_payload,
        "missing_segment_fields": missing_segment,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": budget_ok,
        "llm_call_enabled": item.get("llm_call_enabled"),
    }


def evaluate_stage_c_replay_items(
    items: Sequence[Mapping[str, Any]],
    *,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 12000,
) -> JsonDict:
    scored: List[JsonDict] = []
    for idx, item in enumerate(items or [], start=1):
        q = _as_dict(item.get("input_contract_quality")) or score_stage_c_item(item, max_input_chars=max_input_chars)
        scored.append({
            "idx": idx,
            "id": item.get("highlight_id") or item.get("candidate_id") or item.get("id"),
            "score": q.get("score", 0.0),
            "passed": bool(q.get("passed")),
            "missing_item_fields": q.get("missing_item_fields") or [],
            "missing_payload_fields": q.get("missing_payload_fields") or [],
            "missing_segment_fields": q.get("missing_segment_fields") or [],
            "payload_chars": q.get("payload_chars"),
            "prompt_input_budget_ok": q.get("prompt_input_budget_ok"),
            "llm_call_enabled": q.get("llm_call_enabled"),
        })
    total = len(scored)
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    over_budget = sum(1 for x in scored if not x.get("prompt_input_budget_ok"))
    llm_enabled = sum(1 for x in scored if x.get("llm_call_enabled") is not False)
    return {
        "stage": "stage_c_narration_generation_input_replay",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        "overall_passed": total > 0 and pass_rate >= min_pass_rate and over_budget == 0 and llm_enabled == 0,
        "over_budget_count": over_budget,
        "llm_enabled_count": llm_enabled,
        "required_item_fields": STAGE_C_REQUIRED_ITEM_FIELDS,
        "required_payload_fields": STAGE_C_REQUIRED_PAYLOAD_FIELDS,
        "required_segment_fields": STAGE_C_REQUIRED_SEGMENT_FIELDS,
        "items": scored,
    }


__all__ = [
    "STAGE_C_STAGE_NAME",
    "STAGE_C_REQUIRED_ITEM_FIELDS",
    "STAGE_C_REQUIRED_PAYLOAD_FIELDS",
    "STAGE_C_REQUIRED_SEGMENT_FIELDS",
    "build_stage_c_replay_items",
    "build_narration_generation_replay_item",
    "evaluate_stage_c_replay_items",
    "score_stage_c_item",
]
