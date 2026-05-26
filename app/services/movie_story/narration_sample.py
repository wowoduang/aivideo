from __future__ import annotations

"""Stage-F controlled final narration_generation sample contract.

Stage F is the first *bounded* place where final narration text may be
sample-generated.  It consumes Stage-C legacy narration_generation input packages
and Stage-E whitelisted understanding writebacks.  It does not generate a full
script.  It only proves that:

- Stage-E global/local LLM understanding results can be applied to Stage-C prompt
  payloads;
- a tiny, budgeted subset can call the old narration_generation style prompt;
- generated text is auditable and cannot masquerade as a full production script;
- failed/missing results are reported with precise reasons.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from app.services.movie_story.narration_contract import (
    STAGE_C_PROMPT_NAME,
    STAGE_C_PROMPT_NAMESPACE,
)
from app.services.movie_story.understanding_writeback import (
    STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS,
    STAGE_E_LOCAL_REQUIRED_MIN_FIELDS,
)

JsonDict = Dict[str, Any]

STAGE_F_STAGE_NAME = "07a_narration_generation_sample_contract"
STAGE_F_PROMPT_NAMESPACE = "movie_story_narration"
STAGE_F_PROMPT_NAME = "narration_generation"

STAGE_F_REQUIRED_ITEM_FIELDS = [
    "sample_id",
    "highlight_id",
    "source_stage_c_id",
    "prompt_namespace",
    "prompt_name",
    "llm_call_enabled",
    "llm_cache_key",
    "legacy_prompt_payload",
    "segment_json",
    "project_context",
    "char_budget",
    "stage_e_writeback_applied",
    "narration_result",
    "narration_quality",
]

STAGE_F_REQUIRED_RESULT_FIELDS = [
    "narration",
    "raw_voice_keep",
    "confidence",
    "grounding_notes",
]

STAGE_F_REQUIRED_INPUT_FLAGS = [
    "used_stage_e_global_writeback",
    "used_stage_e_local_writeback",
    "used_narration_intent",
    "used_story_function",
    "used_char_budget",
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


def _as_dict(value: Any) -> JsonDict:
    return dict(value) if isinstance(value, Mapping) else {}


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _json_clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _parse_json_obj(text: str) -> JsonDict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception as _e:
        logger.debug("JSON 解析失败: {}", _e)
    # tolerate fenced JSON / leading explanations
    if "```" in text:
        chunks = [c.strip() for c in text.split("```")]
        for chunk in chunks:
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                try:
                    obj = json.loads(chunk)
                    return obj if isinstance(obj, dict) else {}
                except Exception as _e:
                    logger.debug("JSON 解析失败: {}", _e)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_dir() -> Path:
    return Path(os.environ.get("MOVIE_STORY_STAGE_F_CACHE_DIR") or ".movie_story_stage_f_cache").resolve()


def _writeback_global(stage_e_items: Sequence[Mapping[str, Any]]) -> JsonDict:
    for item in stage_e_items or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("request_type") != "global_story_context_refine":
            continue
        q = _as_dict(item.get("writeback_quality"))
        payload = _as_dict(item.get("writeback_payload"))
        if q.get("passed") and all(_has_value(payload.get(k)) for k in STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS):
            return payload
    return {}


def _writeback_by_highlight(stage_e_items: Sequence[Mapping[str, Any]]) -> Dict[str, JsonDict]:
    out: Dict[str, JsonDict] = {}
    for item in stage_e_items or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("request_type") != "local_understanding_refine":
            continue
        q = _as_dict(item.get("writeback_quality"))
        payload = _as_dict(item.get("writeback_payload"))
        if not (q.get("passed") and all(_has_value(payload.get(k)) for k in STAGE_E_LOCAL_REQUIRED_MIN_FIELDS)):
            continue
        hid = _text(item.get("source_highlight_id") or item.get("highlight_id"))
        if hid:
            out[hid] = payload
    return out


def _apply_writeback_to_stage_c_item(item: Mapping[str, Any], global_writeback: Mapping[str, Any], local_by_hid: Mapping[str, Mapping[str, Any]]) -> Tuple[JsonDict, JsonDict]:
    cur = dict(item)
    payload = _as_dict(cur.get("legacy_prompt_payload"))
    segment = _as_dict(cur.get("segment_json") or payload.get("segment_json"))
    project = _as_dict(cur.get("project_context") or payload.get("project_context"))
    hid = _text(cur.get("highlight_id") or segment.get("highlight_id") or cur.get("candidate_id"))
    local_wb = dict(local_by_hid.get(hid) or {})
    global_wb = dict(global_writeback or {})

    if global_wb:
        payload["global_summary"] = {**_as_dict(payload.get("global_summary")), **global_wb}
        segment["_global_summary"] = {**_as_dict(segment.get("_global_summary")), **global_wb}
        for key in ("main_conflict", "story_theme", "genre", "main_characters", "timeline_summary", "relationship_map", "risk_flags"):
            if _has_value(global_wb.get(key)):
                project[key] = _json_clone(global_wb.get(key))
    if local_wb:
        local = {**_as_dict(segment.get("local_understanding")), **local_wb}
        segment["local_understanding"] = local
        for key, val in local_wb.items():
            if _has_value(val):
                segment[key] = _json_clone(val)
        payload["local_understanding"] = local
        payload["story_function"] = segment.get("story_function")
        payload["narration_intent"] = segment.get("narration_intent")

    payload["segment_json"] = segment
    payload["project_context"] = project
    cur["legacy_prompt_payload"] = payload
    cur["segment_json"] = segment
    cur["project_context"] = project
    flags = {
        "used_stage_e_global_writeback": bool(global_wb),
        "used_stage_e_local_writeback": bool(local_wb),
        "used_narration_intent": bool(_text(segment.get("narration_intent") or payload.get("narration_intent"))),
        "used_story_function": bool(_text(segment.get("story_function") or payload.get("story_function"))),
        "used_char_budget": bool(cur.get("char_budget") or payload.get("char_budget")),
    }
    return cur, flags


def build_stage_f_sample_items(
    stage_c_items: Sequence[Mapping[str, Any]],
    stage_e_items: Sequence[Mapping[str, Any]],
    *,
    min_samples: int = 2,
    max_live_calls: int = 2,
    max_input_chars: int = 12000,
) -> List[JsonDict]:
    """Build bounded final narration-generation sample rows.

    Prefer highlights that have Stage-E local writeback so Stage F proves that
    refined understanding actually reaches final narration prompt input.
    """
    global_wb = _writeback_global(stage_e_items)
    local_by_hid = _writeback_by_highlight(stage_e_items)
    enriched: List[Tuple[JsonDict, JsonDict]] = []
    for raw in stage_c_items or []:
        if not isinstance(raw, Mapping):
            continue
        item, flags = _apply_writeback_to_stage_c_item(raw, global_wb, local_by_hid)
        enriched.append((item, flags))
    # Put rows with local writebacks first, then keep movie order from Stage C.
    enriched.sort(key=lambda pair: (not pair[1].get("used_stage_e_local_writeback"), pair[0].get("start") or 0))
    limit = max(0, min(max_live_calls, max(min_samples, 0)))
    out: List[JsonDict] = []
    for idx, (item, flags) in enumerate(enriched[:limit], start=1):
        payload = _as_dict(item.get("legacy_prompt_payload"))
        segment = _as_dict(item.get("segment_json") or payload.get("segment_json"))
        char_budget = int(item.get("char_budget") or payload.get("char_budget") or 80)
        sample_id = f"stage_f_narration_{idx:03d}_{_text(item.get('highlight_id') or item.get('candidate_id') or idx)}"
        cache_key = "stage_f:" + _stable_hash({
            "prompt": STAGE_F_PROMPT_NAME,
            "highlight_id": item.get("highlight_id"),
            "payload": payload,
            "char_budget": char_budget,
        })
        row: JsonDict = {
            "candidate_id": sample_id,
            "sample_id": sample_id,
            "highlight_id": item.get("highlight_id") or segment.get("highlight_id") or sample_id,
            "source_stage_c_id": item.get("candidate_id") or item.get("highlight_id"),
            "candidate_type": STAGE_F_STAGE_NAME,
            "prompt_namespace": STAGE_F_PROMPT_NAMESPACE,
            "prompt_name": STAGE_F_PROMPT_NAME,
            "llm_call_enabled": True,
            "llm_cache_key": cache_key,
            "legacy_prompt_payload": _json_clone(payload),
            "segment_json": _json_clone(segment),
            "project_context": _json_clone(item.get("project_context") or payload.get("project_context") or {}),
            "style": item.get("style") or payload.get("style") or "short_drama",
            "char_budget": char_budget,
            "stage_e_writeback_applied": flags,
            "payload_chars": len(json.dumps(payload, ensure_ascii=False, default=str)),
            "max_input_chars": max_input_chars,
            "prompt_input_budget_ok": len(json.dumps(payload, ensure_ascii=False, default=str)) <= max_input_chars,
            "narration_result": {},
            "narration_result_source": "missing",
            "narration_quality": {"status": "pending"},
        }
        row["narration_quality"] = score_stage_f_item(row, max_input_chars=max_input_chars)
        out.append(row)
    return out


def _build_narration_prompt(item: Mapping[str, Any]) -> str:
    payload = _as_dict(item.get("legacy_prompt_payload"))
    segment = _as_dict(item.get("segment_json") or payload.get("segment_json"))
    project = _as_dict(item.get("project_context") or payload.get("project_context"))
    char_budget = int(item.get("char_budget") or payload.get("char_budget") or 80)
    safe_budget = max(20, min(char_budget, 160))
    body = {
        "project_context": project,
        "segment_json": segment,
        "style": item.get("style") or payload.get("style") or "short_drama",
        "char_budget": safe_budget,
        "stage_e_writeback_applied": item.get("stage_e_writeback_applied"),
    }
    return (
        "你是旧项目 movie_story_narration/narration_generation 的严格迁移验证器。\n"
        "请只根据给定 evidence 写一段中文影视解说，必须讲剧情功能、冲突推进、人物动机；不要逐句复述字幕；不要提前剧透。\n"
        f"narration 字数建议不超过 {safe_budget} 个中文字符。\n"
        "只输出 JSON，不要 markdown，不要解释。格式：\n"
        "{\"narration\":\"...\",\"raw_voice_keep\":false,\"confidence\":0.0,\"grounding_notes\":[\"...\"]}\n"
        "输入 evidence：\n" + json.dumps(body, ensure_ascii=False, indent=2, default=str)
    )


def _resolve_llm_config(api_key: str = "", base_url: str = "", model: str = "") -> JsonDict:
    from app.services.movie_story.understanding_quality import resolve_stage_d_llm_config
    cfg = resolve_stage_d_llm_config(api_key=api_key, base_url=base_url, model=model)
    return cfg


def maybe_run_live_narration_samples(
    items: Sequence[Mapping[str, Any]],
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    max_live_calls: int = 2,
    timeout: int = 90,
) -> List[JsonDict]:
    try:
        from app.services.llm_text_completion import call_text_chat_completion
    except Exception:
        call_text_chat_completion = None  # type: ignore
    cfg = _resolve_llm_config(api_key=api_key, base_url=base_url, model=model)
    api_key = _text(cfg.get("api_key"))
    base_url = _text(cfg.get("base_url"))
    model = _text(cfg.get("model"))
    cdir = _cache_dir(); cdir.mkdir(parents=True, exist_ok=True)
    out: List[JsonDict] = []
    calls = 0
    for raw in items or []:
        item = dict(raw)
        if item.get("llm_call_enabled") is not True:
            out.append(item); continue
        cache_name = str(item.get("llm_cache_key") or "").replace(":", "_") + ".json"
        cache_path = cdir / cache_name
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and isinstance(cached.get("narration_result"), dict):
                    item.update(cached)
                    item["narration_result_source"] = "cache"
                    item["narration_quality"] = score_stage_f_item(item)
                    if item["narration_quality"].get("passed"):
                        out.append(item); continue
            except Exception as _e:
                logger.debug("JSON 解析失败: {}", _e)
        if calls >= max_live_calls or not (api_key and model and call_text_chat_completion):
            item["narration_result"] = {}
            item["narration_result_source"] = "skipped"
            item["narration_quality"] = score_stage_f_item(item, reason="live_budget_exhausted" if calls >= max_live_calls else "live_config_missing")
            out.append(item); continue
        try:
            raw_text = call_text_chat_completion(
                _build_narration_prompt(item),
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_prompt="你是保守、精准的中文影视解说写作者，只输出 JSON。",
                temperature=0.35,
                timeout=timeout,
                log_label="Stage-F narration_generation 抽样 LLM",
            )
        except Exception as exc:
            item["narration_result"] = {}
            item["narration_result_source"] = "failed"
            item["llm_error"] = str(exc)
            item["narration_quality"] = score_stage_f_item(item, reason="call_exception")
            out.append(item); calls += 1; continue
        calls += 1
        result = _parse_json_obj(raw_text)
        # If model returns bare narration text, keep it but mark parse quality lower.
        if not result and _text(raw_text):
            result = {"narration": _text(raw_text, 240), "raw_voice_keep": False, "confidence": 0.45, "grounding_notes": ["non_json_response_wrapped"]}
        item["narration_result"] = result
        item["llm_raw_response"] = _text(raw_text, 4000)
        item["narration_result_source"] = "live" if result else "failed"
        item["narration_quality"] = score_stage_f_item(item, reason="json_parse_failed" if raw_text and not result else "")
        if result:
            try:
                cache_path.write_text(json.dumps({k: item[k] for k in ["narration_result", "llm_raw_response", "narration_result_source", "narration_quality"] if k in item}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass  # 清理操作，忽略异常
        out.append(item)
    return out


def _narration_text(item: Mapping[str, Any]) -> str:
    result = _as_dict(item.get("narration_result"))
    return _text(result.get("narration"), 500)


def score_stage_f_item(item: Mapping[str, Any], *, max_input_chars: int = 12000, reason: str = "") -> JsonDict:
    missing_item = []
    for key in STAGE_F_REQUIRED_ITEM_FIELDS:
        if key == "narration_result":
            if not isinstance(item.get(key), Mapping) or not item.get(key):
                missing_item.append(key)
            continue
        if key == "llm_call_enabled":
            if item.get(key) is not True:
                missing_item.append("llm_call_enabled_true")
            continue
        if not _has_value(item.get(key)):
            missing_item.append(key)
    result = _as_dict(item.get("narration_result"))
    missing_result = [k for k in STAGE_F_REQUIRED_RESULT_FIELDS if not _has_value(result.get(k))]
    flags = _as_dict(item.get("stage_e_writeback_applied"))
    missing_flags = [k for k in STAGE_F_REQUIRED_INPUT_FLAGS if not flags.get(k)]
    try:
        payload_chars = int(item.get("payload_chars") or len(json.dumps(item.get("legacy_prompt_payload") or {}, ensure_ascii=False, default=str)))
    except Exception:
        payload_chars = max_input_chars + 1
    budget_ok = payload_chars <= max_input_chars
    narration = _narration_text(item)
    char_budget = int(item.get("char_budget") or 80)
    # This is a sample gate, not final quality judging.  Enforce non-empty and a
    # loose upper bound so runaway responses cannot pass.
    narration_chars = len(narration)
    narration_present = narration_chars >= 8
    narration_budget_ok = narration_chars <= max(240, int(char_budget * 3.0))
    confidence = result.get("confidence", 0)
    try:
        conf_ok = float(confidence) >= 0.35
    except Exception:
        conf_ok = False
    score = 0.0
    score += 0.20 if not missing_item else 0.0
    score += 0.20 if not missing_result else 0.0
    score += 0.25 if not missing_flags else max(0.0, 0.25 * (1 - len(missing_flags) / max(1, len(STAGE_F_REQUIRED_INPUT_FLAGS))))
    score += 0.15 if budget_ok else 0.0
    score += 0.10 if narration_present else 0.0
    score += 0.05 if narration_budget_ok else 0.0
    score += 0.05 if conf_ok else 0.0
    score = round(score, 3)
    passed = bool(score >= 0.80 and not missing_result and not missing_flags and budget_ok and narration_present and narration_budget_ok)
    return {
        "score": score,
        "passed": passed,
        "reason": reason,
        "missing_item_fields": missing_item,
        "missing_result_fields": missing_result,
        "missing_input_flags": missing_flags,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": budget_ok,
        "narration_chars": narration_chars,
        "char_budget": char_budget,
        "narration_budget_ok": narration_budget_ok,
        "narration_present": narration_present,
        "confidence_ok": conf_ok,
        "result_source": item.get("narration_result_source"),
    }


def evaluate_stage_f_items(
    items: Sequence[Mapping[str, Any]],
    *,
    min_pass_rate: float = 0.9,
    min_results: int = 2,
    max_llm_calls: int = 2,
    max_input_chars: int = 12000,
) -> JsonDict:
    scored: List[JsonDict] = []
    for idx, item in enumerate(items or [], start=1):
        q = _as_dict(item.get("narration_quality")) or score_stage_f_item(item, max_input_chars=max_input_chars)
        scored.append({
            "idx": idx,
            "id": item.get("sample_id") or item.get("highlight_id") or item.get("candidate_id"),
            "highlight_id": item.get("highlight_id"),
            "score": q.get("score", 0.0),
            "passed": bool(q.get("passed")),
            "missing_item_fields": q.get("missing_item_fields") or [],
            "missing_result_fields": q.get("missing_result_fields") or [],
            "missing_input_flags": q.get("missing_input_flags") or [],
            "payload_chars": q.get("payload_chars"),
            "narration_chars": q.get("narration_chars"),
            "result_source": item.get("narration_result_source"),
            "stage_e_writeback_applied": item.get("stage_e_writeback_applied"),
        })
    total = len(scored)
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    llm_enabled = sum(1 for x in (items or []) if isinstance(x, Mapping) and x.get("llm_call_enabled") is True)
    live_or_cache = sum(1 for x in (items or []) if isinstance(x, Mapping) and x.get("narration_result_source") in {"live", "cache"})
    missing_result = sum(1 for x in scored if "narration_result" in (x.get("missing_item_fields") or []))
    overall = bool(total > 0 and passed >= min_results and live_or_cache >= min_results and llm_enabled <= max_llm_calls)
    return {
        "stage": STAGE_F_STAGE_NAME,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        "overall_passed": overall,
        "min_results": min_results,
        "live_or_cache_result_count": live_or_cache,
        "llm_enabled_count": llm_enabled,
        "max_llm_calls": max_llm_calls,
        "missing_result_count": missing_result,
        "required_item_fields": STAGE_F_REQUIRED_ITEM_FIELDS,
        "required_result_fields": STAGE_F_REQUIRED_RESULT_FIELDS,
        "required_input_flags": STAGE_F_REQUIRED_INPUT_FLAGS,
        "items": scored,
    }


__all__ = [
    "STAGE_F_STAGE_NAME",
    "STAGE_F_REQUIRED_ITEM_FIELDS",
    "STAGE_F_REQUIRED_RESULT_FIELDS",
    "STAGE_F_REQUIRED_INPUT_FLAGS",
    "build_stage_f_sample_items",
    "maybe_run_live_narration_samples",
    "evaluate_stage_f_items",
    "score_stage_f_item",
]
