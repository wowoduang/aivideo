from __future__ import annotations

"""Stage-G controlled narration_validation sample contract.

Stage G consumes Stage-F bounded narration_generation samples and migrates the
old project's post-generation validation layer in a tiny, auditable, budgeted
form.  It does not produce a full script and it does not run TTS/composition.
It proves that generated narration can be checked against the same rich evidence
that produced it, and that review/reject results carry a safe rewrite contract.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from app.services.movie_story.narration_sample import (
    STAGE_F_STAGE_NAME,
    STAGE_F_REQUIRED_INPUT_FLAGS,
)

JsonDict = Dict[str, Any]

STAGE_G_STAGE_NAME = "07b_narration_validation_sample_contract"
STAGE_G_PROMPT_NAMESPACE = "movie_story_narration"
STAGE_G_PROMPT_NAME = "narration_validation"

STAGE_G_REQUIRED_ITEM_FIELDS = [
    "validation_id",
    "sample_id",
    "highlight_id",
    "source_stage_f_id",
    "prompt_namespace",
    "prompt_name",
    "llm_call_enabled",
    "llm_cache_key",
    "validation_prompt_payload",
    "segment_json",
    "narration_result",
    "validation_result",
    "validation_quality",
]

STAGE_G_REQUIRED_RESULT_FIELDS = [
    "status",
    "issues",
    "safe_rewrite_hint",
    "grounding_score",
    "evidence_notes",
]

STAGE_G_REQUIRED_INPUT_FLAGS = [
    "used_source_narration",
    "used_segment_evidence",
    "used_stage_e_writeback",
    "used_narration_intent",
    "used_story_function",
]

STAGE_G_STATUS_VALUES = {"pass", "review", "reject"}


def _text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
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
    except Exception:
        pass
    if "```" in text:
        for chunk in [c.strip() for c in text.split("```")]:
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                try:
                    obj = json.loads(chunk)
                    return obj if isinstance(obj, dict) else {}
                except Exception:
                    pass
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
    return Path(os.environ.get("MOVIE_STORY_STAGE_G_CACHE_DIR") or ".movie_story_stage_g_cache").resolve()


def _narration_text(item: Mapping[str, Any]) -> str:
    result = _as_dict(item.get("narration_result"))
    return _text(result.get("narration"), 800)


def _writeback_flags(item: Mapping[str, Any]) -> JsonDict:
    flags = _as_dict(item.get("stage_e_writeback_applied"))
    return {
        "used_source_narration": bool(_narration_text(item)),
        "used_segment_evidence": bool(_as_dict(item.get("segment_json"))),
        "used_stage_e_writeback": bool(flags.get("used_stage_e_global_writeback") and flags.get("used_stage_e_local_writeback")),
        "used_narration_intent": bool(flags.get("used_narration_intent") or _text(_as_dict(item.get("segment_json")).get("narration_intent"))),
        "used_story_function": bool(flags.get("used_story_function") or _text(_as_dict(item.get("segment_json")).get("story_function"))),
    }


def build_stage_g_validation_items(
    stage_f_items: Sequence[Mapping[str, Any]],
    *,
    min_samples: int = 2,
    max_live_calls: int = 2,
    max_input_chars: int = 12000,
) -> List[JsonDict]:
    """Build bounded validation rows from Stage-F narration samples."""
    usable: List[Mapping[str, Any]] = []
    for raw in stage_f_items or []:
        if not isinstance(raw, Mapping):
            continue
        q = _as_dict(raw.get("narration_quality"))
        if q.get("passed") and _narration_text(raw):
            usable.append(raw)
    limit = max(0, min(max_live_calls, max(min_samples, 0)))
    out: List[JsonDict] = []
    for idx, item in enumerate(usable[:limit], start=1):
        segment = _as_dict(item.get("segment_json"))
        narration_result = _as_dict(item.get("narration_result"))
        payload = {
            "segment_json": _json_clone(segment),
            "project_context": _json_clone(item.get("project_context") or {}),
            "narration_result": _json_clone(narration_result),
            "narration": _narration_text(item),
            "char_budget": item.get("char_budget"),
            "stage_e_writeback_applied": _json_clone(item.get("stage_e_writeback_applied") or {}),
            "validation_focus": [
                "是否基于证据，没有编造人物关系或因果",
                "是否偏离当前时间窗或提前剧透",
                "是否解释剧情功能、冲突推进、人物动机",
                "是否过度复述字幕",
                "raw_voice_keep 是否与情绪/原声策略一致",
            ],
        }
        validation_id = f"stage_g_validation_{idx:03d}_{_text(item.get('highlight_id') or item.get('sample_id') or idx)}"
        cache_key = "stage_g:" + _stable_hash({
            "prompt": STAGE_G_PROMPT_NAME,
            "source_stage_f_id": item.get("sample_id"),
            "highlight_id": item.get("highlight_id"),
            "payload": payload,
        })
        row: JsonDict = {
            "candidate_id": validation_id,
            "validation_id": validation_id,
            "sample_id": item.get("sample_id") or validation_id,
            "highlight_id": item.get("highlight_id") or segment.get("highlight_id") or validation_id,
            "source_stage_f_id": item.get("sample_id") or item.get("candidate_id") or item.get("highlight_id"),
            "candidate_type": STAGE_G_STAGE_NAME,
            "prompt_namespace": STAGE_G_PROMPT_NAMESPACE,
            "prompt_name": STAGE_G_PROMPT_NAME,
            "llm_call_enabled": True,
            "llm_cache_key": cache_key,
            "validation_prompt_payload": payload,
            "segment_json": _json_clone(segment),
            "narration_result": _json_clone(narration_result),
            "input_flags": _writeback_flags(item),
            "payload_chars": len(json.dumps(payload, ensure_ascii=False, default=str)),
            "max_input_chars": max_input_chars,
            "prompt_input_budget_ok": len(json.dumps(payload, ensure_ascii=False, default=str)) <= max_input_chars,
            "validation_result": {},
            "validation_result_source": "missing",
            "validation_quality": {"status": "pending"},
        }
        row["validation_quality"] = score_stage_g_item(row, max_input_chars=max_input_chars)
        out.append(row)
    return out


def _build_validation_prompt(item: Mapping[str, Any]) -> str:
    payload = _as_dict(item.get("validation_prompt_payload"))
    return (
        "你是旧项目 movie_story_narration/narration_validation 的严格迁移验证器。\n"
        "请只根据给定 evidence 校验 narration。不要重写整段，只给出状态、问题和安全重写建议。\n"
        "输出必须是 JSON，不要 markdown，不要解释。格式：\n"
        "{\"status\":\"pass|review|reject\",\"issues\":[\"...\"],\"safe_rewrite_hint\":\"...\",\"grounding_score\":0.0,\"raw_voice_keep\":false,\"evidence_notes\":[\"...\"]}\n"
        "判定规则：pass=证据充分且没有明显风险；review=基本可用但建议小改；reject=存在编造、剧透、错误归因或严重复述。\n"
        "输入：\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )


def _resolve_llm_config(api_key: str = "", base_url: str = "", model: str = "") -> JsonDict:
    from app.services.movie_story.understanding_quality import resolve_stage_d_llm_config
    return resolve_stage_d_llm_config(api_key=api_key, base_url=base_url, model=model)


def _normalize_validation_result(result: JsonDict) -> JsonDict:
    if not isinstance(result, dict):
        return {}
    out = dict(result)
    status = _text(out.get("status")).lower()
    if status not in STAGE_G_STATUS_VALUES:
        # Some Chinese responses may use words like 通过/需修改/拒绝.
        raw = _text(out.get("status")) + " " + _text(out.get("issues"))
        if any(k in raw for k in ["reject", "拒绝", "错误", "编造", "剧透"]):
            status = "reject"
        elif any(k in raw for k in ["review", "修改", "建议", "复核"]):
            status = "review"
        elif any(k in raw for k in ["pass", "通过", "可用"]):
            status = "pass"
        else:
            status = "review" if result else ""
    if status:
        out["status"] = status
    if not isinstance(out.get("issues"), list):
        issue_text = _text(out.get("issues"))
        out["issues"] = [issue_text] if issue_text else []
    if not isinstance(out.get("evidence_notes"), list):
        note_text = _text(out.get("evidence_notes") or out.get("grounding_notes"))
        out["evidence_notes"] = [note_text] if note_text else []
    if "grounding_score" not in out and "confidence" in out:
        out["grounding_score"] = out.get("confidence")
    if "safe_rewrite_hint" not in out:
        out["safe_rewrite_hint"] = ""
    return out


def maybe_run_live_validation_samples(
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
                if isinstance(cached, dict) and isinstance(cached.get("validation_result"), dict):
                    item.update(cached)
                    item["validation_result_source"] = "cache"
                    item["validation_quality"] = score_stage_g_item(item)
                    if item["validation_quality"].get("passed"):
                        out.append(item); continue
            except Exception:
                pass
        if calls >= max_live_calls or not (api_key and model and call_text_chat_completion):
            item["validation_result"] = {}
            item["validation_result_source"] = "skipped"
            item["validation_quality"] = score_stage_g_item(item, reason="live_budget_exhausted" if calls >= max_live_calls else "live_config_missing")
            out.append(item); continue
        try:
            raw_text = call_text_chat_completion(
                _build_validation_prompt(item),
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_prompt="你是保守、严格的中文影视解说校验器，只输出 JSON。",
                temperature=0.2,
                timeout=timeout,
                log_label="Stage-G narration_validation 抽样 LLM",
            )
        except Exception as exc:
            item["validation_result"] = {}
            item["validation_result_source"] = "failed"
            item["llm_error"] = str(exc)
            item["validation_quality"] = score_stage_g_item(item, reason="call_exception")
            out.append(item); calls += 1; continue
        calls += 1
        result = _normalize_validation_result(_parse_json_obj(raw_text))
        if not result and _text(raw_text):
            result = {
                "status": "review",
                "issues": ["non_json_response_wrapped"],
                "safe_rewrite_hint": _text(raw_text, 240),
                "grounding_score": 0.4,
                "raw_voice_keep": False,
                "evidence_notes": ["模型未按 JSON 返回，已包装为 review"],
            }
        item["validation_result"] = result
        item["llm_raw_response"] = _text(raw_text, 4000)
        item["validation_result_source"] = "live" if result else "failed"
        item["validation_quality"] = score_stage_g_item(item, reason="json_parse_failed" if raw_text and not result else "")
        if result:
            try:
                cache_path.write_text(json.dumps({k: item[k] for k in ["validation_result", "llm_raw_response", "validation_result_source", "validation_quality"] if k in item}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        out.append(item)
    return out


def score_stage_g_item(item: Mapping[str, Any], *, max_input_chars: int = 12000, reason: str = "") -> JsonDict:
    missing_item = []
    for key in STAGE_G_REQUIRED_ITEM_FIELDS:
        if key == "validation_result":
            if not isinstance(item.get(key), Mapping) or not item.get(key):
                missing_item.append(key)
            continue
        if key == "llm_call_enabled":
            if item.get(key) is not True:
                missing_item.append("llm_call_enabled_true")
            continue
        if not _has_value(item.get(key)):
            missing_item.append(key)
    result = _normalize_validation_result(_as_dict(item.get("validation_result")))
    status = _text(result.get("status")).lower()
    # Stage-G validation semantics:
    # - For pass results, an empty issues list is valid and expected.
    # - For pass results, an empty safe_rewrite_hint is valid because no rewrite is required.
    # - For review/reject results, safe_rewrite_hint must be non-empty so Stage-H can rewrite safely.
    missing_result = []
    for k in STAGE_G_REQUIRED_RESULT_FIELDS:
        if k == "issues":
            if "issues" not in result or not isinstance(result.get("issues"), list):
                missing_result.append(k)
            continue
        if k == "safe_rewrite_hint":
            if "safe_rewrite_hint" not in result:
                missing_result.append(k)
            continue
        if not _has_value(result.get(k)):
            missing_result.append(k)
    status_ok = status in STAGE_G_STATUS_VALUES
    try:
        grounding = float(result.get("grounding_score"))
    except Exception:
        grounding = -1.0
    grounding_ok = 0.0 <= grounding <= 1.0
    flags = _as_dict(item.get("input_flags"))
    missing_flags = [k for k in STAGE_G_REQUIRED_INPUT_FLAGS if not flags.get(k)]
    try:
        payload_chars = int(item.get("payload_chars") or len(json.dumps(item.get("validation_prompt_payload") or {}, ensure_ascii=False, default=str)))
    except Exception:
        payload_chars = max_input_chars + 1
    budget_ok = payload_chars <= max_input_chars
    review_rewrite_ok = True
    if status in {"review", "reject"}:
        review_rewrite_ok = bool(_text(result.get("safe_rewrite_hint"), 12))
    score = 0.0
    score += 0.20 if not missing_item else 0.0
    score += 0.25 if not missing_result else 0.0
    score += 0.20 if not missing_flags else max(0.0, 0.20 * (1 - len(missing_flags) / max(1, len(STAGE_G_REQUIRED_INPUT_FLAGS))))
    score += 0.10 if status_ok else 0.0
    score += 0.10 if grounding_ok else 0.0
    score += 0.10 if budget_ok else 0.0
    score += 0.05 if review_rewrite_ok else 0.0
    score = round(score, 3)
    passed = bool(score >= 0.80 and not missing_result and not missing_flags and status_ok and grounding_ok and budget_ok and review_rewrite_ok)
    return {
        "score": score,
        "passed": passed,
        "reason": reason,
        "missing_item_fields": missing_item,
        "missing_result_fields": missing_result,
        "missing_input_flags": missing_flags,
        "status": status,
        "status_ok": status_ok,
        "grounding_score": grounding,
        "grounding_ok": grounding_ok,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": budget_ok,
        "review_rewrite_ok": review_rewrite_ok,
        "result_source": item.get("validation_result_source"),
    }


def evaluate_stage_g_items(
    items: Sequence[Mapping[str, Any]],
    *,
    min_pass_rate: float = 0.9,
    min_results: int = 2,
    max_llm_calls: int = 2,
    max_input_chars: int = 12000,
) -> JsonDict:
    scored: List[JsonDict] = []
    passed = 0
    live_or_cache = 0
    llm_enabled = 0
    missing_result = 0
    review_or_reject = 0
    rewrite_ready = 0
    status_counts: Dict[str, int] = {}
    for raw in items or []:
        item = dict(raw)
        if item.get("llm_call_enabled") is True:
            llm_enabled += 1
        if item.get("validation_result_source") in {"live", "cache"}:
            live_or_cache += 1
        q = _as_dict(item.get("validation_quality")) or score_stage_g_item(item, max_input_chars=max_input_chars)
        if not q:
            q = score_stage_g_item(item, max_input_chars=max_input_chars)
        item["validation_quality"] = q
        result = _normalize_validation_result(_as_dict(item.get("validation_result")))
        status = _text(result.get("status")).lower() or "missing"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in {"review", "reject"}:
            review_or_reject += 1
            if q.get("review_rewrite_ok"):
                rewrite_ready += 1
        if q.get("passed"):
            passed += 1
        if not _as_dict(item.get("validation_result")):
            missing_result += 1
        scored.append(item)
    total = len(scored)
    pass_rate = round(passed / total, 3) if total else 0.0
    overall = bool(total and passed >= min_results and pass_rate >= min_pass_rate and live_or_cache >= min_results and llm_enabled <= max_llm_calls)
    return {
        "stage": STAGE_G_STAGE_NAME,
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
        "review_or_reject_count": review_or_reject,
        "rewrite_ready_count": rewrite_ready,
        "status_counts": status_counts,
        "required_item_fields": STAGE_G_REQUIRED_ITEM_FIELDS,
        "required_result_fields": STAGE_G_REQUIRED_RESULT_FIELDS,
        "required_input_flags": STAGE_G_REQUIRED_INPUT_FLAGS,
        "items": scored,
    }


__all__ = [
    "STAGE_G_STAGE_NAME",
    "STAGE_G_REQUIRED_ITEM_FIELDS",
    "STAGE_G_REQUIRED_RESULT_FIELDS",
    "STAGE_G_REQUIRED_INPUT_FLAGS",
    "build_stage_g_validation_items",
    "maybe_run_live_validation_samples",
    "evaluate_stage_g_items",
    "score_stage_g_item",
]
