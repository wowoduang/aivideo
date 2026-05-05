from __future__ import annotations

"""Stage-D legacy global/local understanding quality sampling.

Stage D is the first controlled re-introduction point for the old project's
LLM-driven *understanding* layer.  It still does not generate final narration.

What it verifies:
- a global-understanding refinement request can be built from real Stage-C data;
- bounded local-understanding refinement requests can be built for sampled highlights;
- every request has a stable cache key and token/input budget;
- live LLM calls are off by default and can be enabled only with an explicit flag.

This lets us migrate old-project global_summary/add_local_understanding quality
without spending tokens during every structural test run.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

JsonDict = Dict[str, Any]

STAGE_D_STAGE_NAME = "06c_understanding_quality_sample_contract"
STAGE_D_PROMPT_NAMESPACE = "movie_story_understanding"
STAGE_D_GLOBAL_PROMPT = "global_story_context_refine"
STAGE_D_LOCAL_PROMPT = "local_understanding_refine"

STAGE_D_REQUIRED_ITEM_FIELDS = [
    "sample_id",
    "request_type",
    "prompt_namespace",
    "prompt_name",
    "llm_call_enabled",
    "llm_cache_key",
    "prompt_payload",
    "payload_chars",
    "max_input_chars",
    "quality_targets",
    "understanding_contract_quality",
]

STAGE_D_REQUIRED_PAYLOAD_FIELDS = {
    STAGE_D_GLOBAL_PROMPT: [
        "current_global_summary",
        "timeline_summary",
        "main_conflict",
        "genre",
        "main_characters",
        "sample_segments",
        "expected_output_fields",
    ],
    STAGE_D_LOCAL_PROMPT: [
        "current_global_summary",
        "segment_json",
        "subtitle_text",
        "surface_dialogue_meaning",
        "real_narrative_state",
        "conflict_summary",
        "character_motivation",
        "story_function",
        "narration_intent",
        "expected_output_fields",
    ],
}

STAGE_D_GLOBAL_TARGET_FIELDS = [
    "main_conflict",
    "story_theme",
    "genre",
    "main_characters",
    "timeline_summary",
    "relationship_map",
    "risk_flags",
]

STAGE_D_LOCAL_TARGET_FIELDS = [
    "surface_dialogue_meaning",
    "real_narrative_state",
    "conflict_summary",
    "character_motivation",
    "story_function",
    "plot_function",
    "importance_level",
    "narration_intent",
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


def _cache_key(payload: Mapping[str, Any], prompt_name: str) -> str:
    raw = json.dumps({"prompt": prompt_name, "payload": payload}, ensure_ascii=False, sort_keys=True, default=str)
    return "stage_d:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stage_c_payload(item: Mapping[str, Any]) -> JsonDict:
    payload = _as_dict(item.get("legacy_prompt_payload"))
    if payload:
        return payload
    segment = _as_dict(item.get("segment_json"))
    return {
        "segment_json": segment,
        "project_context": _as_dict(item.get("project_context")),
        "global_summary": _as_dict(item.get("global_summary") or segment.get("_global_summary")),
        "local_understanding": _as_dict(item.get("local_understanding") or segment.get("local_understanding")),
        "narration_intent": item.get("narration_intent") or segment.get("narration_intent"),
        "selection_reason": item.get("selection_reason") or segment.get("selection_reason"),
    }


def _segment_json(item: Mapping[str, Any]) -> JsonDict:
    return _as_dict(_stage_c_payload(item).get("segment_json"))


def _global_summary_from_items(items: Sequence[Mapping[str, Any]], global_summary: Mapping[str, Any] | None = None) -> JsonDict:
    gs = _as_dict(global_summary)
    if gs:
        return gs
    for item in items or []:
        payload = _stage_c_payload(item)
        candidate = _as_dict(payload.get("global_summary")) or _as_dict(_segment_json(item).get("_global_summary"))
        if candidate:
            return candidate
    return {}


def _baseline_presence(payload: Mapping[str, Any], target_fields: Sequence[str]) -> JsonDict:
    present = [key for key in target_fields if _has_value(payload.get(key))]
    missing = [key for key in target_fields if key not in present]
    return {"present": present, "missing": missing, "score": round(len(present) / max(1, len(target_fields)), 3)}


def _make_item(
    *,
    sample_id: str,
    request_type: str,
    prompt_name: str,
    prompt_payload: Mapping[str, Any],
    quality_targets: Sequence[str],
    llm_call_enabled: bool,
    max_input_chars: int,
    source_highlight_id: str = "",
    sample_rank: int = 0,
) -> JsonDict:
    payload = _json_clone(prompt_payload)
    payload_chars = len(json.dumps(payload, ensure_ascii=False, default=str))
    item: JsonDict = {
        "sample_id": sample_id,
        "candidate_id": sample_id,
        "highlight_id": source_highlight_id or sample_id,
        "source_highlight_id": source_highlight_id,
        "sample_rank": sample_rank,
        "request_type": request_type,
        "candidate_type": "stage_d_understanding_quality_sample_contract",
        "prompt_namespace": STAGE_D_PROMPT_NAMESPACE,
        "prompt_name": prompt_name,
        "llm_call_enabled": bool(llm_call_enabled),
        "llm_disabled_reason": "stage_d_contract_and_cache_check" if not llm_call_enabled else "live_sampling_budgeted_by_stage_d",
        "llm_cache_key": _cache_key(payload, prompt_name),
        "cache_policy": "cache_required_before_live_llm",
        "prompt_payload": payload,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": payload_chars <= max_input_chars,
        "quality_targets": list(quality_targets),
        "baseline_presence": _baseline_presence(payload, quality_targets),
        "understanding_contract_quality": {"status": "pending"},
    }
    item["understanding_contract_quality"] = score_stage_d_item(item, max_input_chars=max_input_chars)
    return item


def _rank_for_sampling(items: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Prefer diverse/high-value records, but keep chronological stability."""
    def score(item: Mapping[str, Any]) -> tuple:
        seg = _segment_json(item)
        text = _text(seg.get("subtitle_text"))
        role = _text(seg.get("story_role") or seg.get("story_function") or seg.get("plot_function"))
        imp = _text(seg.get("importance_level")).lower()
        val = 0
        if imp == "high":
            val += 4
        if any(k in role for k in ["冲突", "反转", "信息", "情绪", "伏笔", "收束"]):
            val += 3
        if text:
            val += min(3, len(text) // 40)
        try:
            start = float(seg.get("start") or 0.0)
        except Exception:
            start = 0.0
        return (-val, start)
    return sorted([x for x in items or [] if isinstance(x, Mapping)], key=score)


def build_stage_d_understanding_items(
    stage_c_items: Sequence[Mapping[str, Any]],
    global_summary: Mapping[str, Any] | None = None,
    *,
    max_local_samples: int = 8,
    llm_call_enabled: bool = False,
    max_input_chars: int = 9000,
) -> List[JsonDict]:
    items = [x for x in (stage_c_items or []) if isinstance(x, Mapping)]
    ranked_items = _rank_for_sampling(items)
    gs = _global_summary_from_items(items, global_summary)
    sample_segments: List[JsonDict] = []
    for item in ranked_items[: max(1, max_local_samples)]:
        seg = _segment_json(item)
        if seg:
            sample_segments.append({
                "highlight_id": seg.get("highlight_id"),
                "timestamp": seg.get("timestamp"),
                "subtitle_text": _text(seg.get("subtitle_text"), 500),
                "real_narrative_state": _text(seg.get("real_narrative_state"), 360),
                "story_function": _text(seg.get("story_function"), 180),
                "selection_reason": _text(seg.get("selection_reason"), 260),
            })

    global_payload = {
        "current_global_summary": gs,
        "main_conflict": gs.get("main_conflict") or "",
        "story_theme": gs.get("story_theme") or "",
        "genre": gs.get("genre") or "",
        "main_characters": gs.get("main_characters") or [],
        "timeline_summary": gs.get("timeline_summary") or [],
        "relationship_map": gs.get("relationship_map") or [],
        "risk_flags": gs.get("risk_flags") or [],
        "sample_segments": sample_segments,
        "migration_instruction": "Refine legacy global story understanding. Preserve facts from evidence; do not create final narration text.",
        "expected_output_fields": STAGE_D_GLOBAL_TARGET_FIELDS,
    }
    out: List[JsonDict] = [
        _make_item(
            sample_id="stage_d_global_context_refine",
            request_type="global_story_context_refine",
            prompt_name=STAGE_D_GLOBAL_PROMPT,
            prompt_payload=global_payload,
            quality_targets=STAGE_D_GLOBAL_TARGET_FIELDS,
            llm_call_enabled=llm_call_enabled,
            max_input_chars=max_input_chars,
            sample_rank=0,
        )
    ]

    for idx, item in enumerate(ranked_items[: max(0, max_local_samples)], start=1):
        payload = _stage_c_payload(item)
        seg = _as_dict(payload.get("segment_json"))
        local = _as_dict(payload.get("local_understanding")) or _as_dict(seg.get("local_understanding"))
        hid = _text(seg.get("highlight_id") or item.get("highlight_id") or f"sample_{idx:03d}")
        local_payload = {
            "current_global_summary": gs,
            "segment_json": seg,
            "local_understanding": local,
            "subtitle_text": seg.get("subtitle_text") or "",
            "surface_dialogue_meaning": seg.get("surface_dialogue_meaning") or local.get("surface_dialogue_meaning") or "",
            "real_narrative_state": seg.get("real_narrative_state") or local.get("real_narrative_state") or "",
            "conflict_summary": seg.get("conflict_summary") or local.get("conflict_summary") or "",
            "character_motivation": seg.get("character_motivation") or local.get("character_motivation") or "",
            "story_function": seg.get("story_function") or local.get("story_function") or "",
            "plot_function": seg.get("plot_function") or "",
            "importance_level": seg.get("importance_level") or "",
            "narration_intent": seg.get("narration_intent") or payload.get("narration_intent") or "",
            "selection_reason": seg.get("selection_reason") or payload.get("selection_reason") or "",
            "migration_instruction": "Refine legacy local_understanding for this segment. Explain narrative state, motivation, conflict, and story function. Do not write final narration.",
            "expected_output_fields": STAGE_D_LOCAL_TARGET_FIELDS,
        }
        out.append(
            _make_item(
                sample_id=f"stage_d_local_{idx:03d}_{hid}",
                request_type="local_understanding_refine",
                prompt_name=STAGE_D_LOCAL_PROMPT,
                prompt_payload=local_payload,
                quality_targets=STAGE_D_LOCAL_TARGET_FIELDS,
                llm_call_enabled=llm_call_enabled,
                max_input_chars=max_input_chars,
                source_highlight_id=hid,
                sample_rank=idx,
            )
        )
    return out


def score_stage_d_item(item: Mapping[str, Any], *, max_input_chars: int = 9000) -> JsonDict:
    missing_item: List[str] = []
    for key in STAGE_D_REQUIRED_ITEM_FIELDS:
        if key == "llm_call_enabled":
            if item.get(key) not in (True, False):
                missing_item.append(key)
            continue
        if not _has_value(item.get(key)):
            missing_item.append(key)

    prompt_name = _text(item.get("prompt_name"))
    payload = _as_dict(item.get("prompt_payload"))
    required_payload = STAGE_D_REQUIRED_PAYLOAD_FIELDS.get(prompt_name, [])
    missing_payload = [key for key in required_payload if not _has_value(payload.get(key))]
    targets = list(item.get("quality_targets") or [])
    expected_targets = STAGE_D_GLOBAL_TARGET_FIELDS if prompt_name == STAGE_D_GLOBAL_PROMPT else STAGE_D_LOCAL_TARGET_FIELDS
    missing_targets = [key for key in expected_targets if key not in targets]
    try:
        payload_chars = int(item.get("payload_chars") or len(json.dumps(payload, ensure_ascii=False, default=str)))
    except Exception:
        payload_chars = max_input_chars + 1
    budget_ok = payload_chars <= max_input_chars
    has_cache = bool(_text(item.get("llm_cache_key")))

    item_score = 1.0 - (len(missing_item) / max(1, len(STAGE_D_REQUIRED_ITEM_FIELDS)))
    payload_score = 1.0 - (len(missing_payload) / max(1, len(required_payload) or 1))
    target_score = 1.0 - (len(missing_targets) / max(1, len(expected_targets)))
    score = round(max(0.0, item_score * 0.3 + payload_score * 0.35 + target_score * 0.2 + (0.1 if budget_ok else 0.0) + (0.05 if has_cache else 0.0)), 3)
    passed = score >= 0.9 and not missing_item and len(missing_payload) <= 1 and not missing_targets and budget_ok and has_cache
    return {
        "score": score,
        "passed": passed,
        "missing_item_fields": missing_item,
        "missing_payload_fields": missing_payload,
        "missing_target_fields": missing_targets,
        "payload_chars": payload_chars,
        "max_input_chars": max_input_chars,
        "prompt_input_budget_ok": budget_ok,
        "llm_call_enabled": item.get("llm_call_enabled"),
        "has_cache_key": has_cache,
        "request_type": item.get("request_type"),
    }


def evaluate_stage_d_items(
    items: Sequence[Mapping[str, Any]],
    *,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 9000,
    max_llm_calls: int = 0,
    min_local_samples: int = 6,
) -> JsonDict:
    scored: List[JsonDict] = []
    for idx, item in enumerate(items or [], start=1):
        q = _as_dict(item.get("understanding_contract_quality")) or score_stage_d_item(item, max_input_chars=max_input_chars)
        scored.append({
            "idx": idx,
            "id": item.get("sample_id") or item.get("candidate_id") or item.get("id"),
            "request_type": item.get("request_type"),
            "prompt_name": item.get("prompt_name"),
            "score": q.get("score", 0.0),
            "passed": bool(q.get("passed")),
            "missing_item_fields": q.get("missing_item_fields") or [],
            "missing_payload_fields": q.get("missing_payload_fields") or [],
            "missing_target_fields": q.get("missing_target_fields") or [],
            "payload_chars": q.get("payload_chars"),
            "prompt_input_budget_ok": q.get("prompt_input_budget_ok"),
            "llm_call_enabled": q.get("llm_call_enabled"),
            "has_cache_key": q.get("has_cache_key"),
            "source_highlight_id": item.get("source_highlight_id"),
        })
    total = len(scored)
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    global_count = sum(1 for x in scored if x.get("request_type") == "global_story_context_refine")
    local_count = sum(1 for x in scored if x.get("request_type") == "local_understanding_refine")
    over_budget = sum(1 for x in scored if not x.get("prompt_input_budget_ok"))
    llm_enabled = sum(1 for x in scored if x.get("llm_call_enabled") is True)
    cache_ready = sum(1 for x in scored if x.get("has_cache_key"))
    return {
        "stage": "stage_d_understanding_quality_sample_contract",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        "overall_passed": (
            total > 0
            and pass_rate >= min_pass_rate
            and global_count >= 1
            and local_count >= min_local_samples
            and over_budget == 0
            and llm_enabled <= max_llm_calls
            and cache_ready == total
        ),
        "global_request_count": global_count,
        "local_sample_count": local_count,
        "min_local_samples": min_local_samples,
        "over_budget_count": over_budget,
        "llm_enabled_count": llm_enabled,
        "max_llm_calls": max_llm_calls,
        "cache_ready_count": cache_ready,
        "required_item_fields": STAGE_D_REQUIRED_ITEM_FIELDS,
        "required_payload_fields": STAGE_D_REQUIRED_PAYLOAD_FIELDS,
        "global_target_fields": STAGE_D_GLOBAL_TARGET_FIELDS,
        "local_target_fields": STAGE_D_LOCAL_TARGET_FIELDS,
        "items": scored,
    }


def _build_llm_prompt(item: Mapping[str, Any]) -> str:
    request_type = _text(item.get("request_type"))
    payload = _as_dict(item.get("prompt_payload"))
    expected = payload.get("expected_output_fields") or []
    if request_type == "global_story_context_refine":
        task = "请基于真实字幕证据，修正全局剧情理解。不要写最终解说词。"
    else:
        task = "请基于当前片段和全局剧情，修正局部剧情理解。不要写最终解说词。"
    return (
        f"{task}\n"
        "必须只输出 JSON，不要输出 Markdown。\n"
        f"输出字段必须包含：{json.dumps(expected, ensure_ascii=False)}\n"
        "事实必须来自输入 evidence；不确定人物身份时用中性称呼。\n"
        "输入如下：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
    )


def _parse_json_obj(raw: str) -> JsonDict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start:end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _cache_dir() -> Path:
    root = os.environ.get("MOVIE_STORY_STAGE_D_CACHE_DIR", "")
    if root:
        path = Path(root)
    else:
        path = Path(".cache") / "movie_story" / "stage_d_llm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _env_first(*names: str) -> str:
    for name in names:
        val = os.environ.get(name)
        if val:
            return str(val).strip()
    return ""


def resolve_stage_d_llm_config(
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> JsonDict:
    """Resolve Stage-D understanding LLM config with explicit env fallback.

    The backend may be started from a different shell than the verification
    command.  Stage E therefore needs an explicit post-run tool and robust
    env/config resolution.  This function prefers parameters, then Stage-D
    env vars, then generic text-LLM env vars, then app config.
    """
    cfg: JsonDict = {}
    try:
        from app.services.llm_config import get_text_llm_config
        raw_cfg = get_text_llm_config() or {}
        if isinstance(raw_cfg, Mapping):
            cfg = dict(raw_cfg)
    except Exception:
        cfg = {}

    resolved = {
        "api_key": _text(api_key) or _env_first(
            "MOVIE_STORY_STAGE_D_API_KEY",
            "MOVIE_STORY_TEXT_LLM_API_KEY",
            "TEXT_LITELLM_API_KEY",
            "OPENAI_API_KEY",
            "DASHSCOPE_API_KEY",
            "QWEN_API_KEY",
        ) or _text(cfg.get("api_key")),
        "base_url": _text(base_url) or _env_first(
            "MOVIE_STORY_STAGE_D_BASE_URL",
            "MOVIE_STORY_TEXT_LLM_BASE_URL",
            "TEXT_LITELLM_BASE_URL",
            "OPENAI_BASE_URL",
            "DASHSCOPE_BASE_URL",
            "QWEN_BASE_URL",
        ) or _text(cfg.get("base_url")),
        "model": _text(model) or _env_first(
            "MOVIE_STORY_STAGE_D_MODEL",
            "MOVIE_STORY_TEXT_LLM_MODEL",
            "TEXT_LITELLM_MODEL_NAME",
            "OPENAI_MODEL",
            "DASHSCOPE_MODEL",
            "QWEN_MODEL",
        ) or _text(cfg.get("model")),
        "provider": _text(cfg.get("provider")),
    }
    resolved["ready"] = bool(resolved.get("api_key") and resolved.get("model"))
    return resolved



def _required_min_fields_for_prompt(prompt_name: str, request_type: str = "") -> List[str]:
    """Minimum fields needed for Stage-E writeback validation.

    This intentionally mirrors Stage-E's tiny-budget gate.  Stage-D cache files
    from earlier diagnostic runs may contain review/empty results; those must
    not block live refresh just because a cache file exists.
    """
    if prompt_name == STAGE_D_GLOBAL_PROMPT or request_type == "global_story_context_refine":
        return ["main_conflict", "story_theme", "genre", "timeline_summary"]
    return ["surface_dialogue_meaning", "real_narrative_state", "conflict_summary", "character_motivation", "story_function"]


def _extract_cached_result(candidate: Mapping[str, Any]) -> JsonDict:
    for key in ("llm_result", "refined_understanding", "result", "writeback_result"):
        val = candidate.get(key)
        if isinstance(val, Mapping):
            return dict(val)
        if isinstance(val, str) and val.strip().startswith("{"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return {}


def _cache_result_is_stage_e_ready(candidate: Mapping[str, Any], *, prompt_name: str, request_type: str) -> JsonDict:
    result = _extract_cached_result(candidate)
    required = _required_min_fields_for_prompt(prompt_name, request_type)
    missing = [key for key in required if not _has_value(result.get(key))]
    return {
        "ready": bool(result and not missing),
        "missing_min_fields": missing,
        "present_fields": [key for key in required if _has_value(result.get(key))],
        "required_min_fields": required,
    }

def maybe_run_live_understanding_samples(
    items: Sequence[Mapping[str, Any]],
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    max_live_calls: int = 0,
    timeout: int = 90,
) -> List[JsonDict]:
    """Optional live Stage-D LLM sampling with cache.

    This is deliberately opt-in.  It never calls final narration generation.  It
    only fills ``llm_result`` / ``llm_result_quality`` on Stage-D understanding
    samples so the migration can compare real old-logic understanding quality.
    """
    try:
        from app.services.llm_config import get_text_llm_config
        from app.services.llm_text_completion import call_text_chat_completion
    except Exception:
        get_text_llm_config = None  # type: ignore
        call_text_chat_completion = None  # type: ignore

    resolved_cfg = resolve_stage_d_llm_config(api_key=api_key, base_url=base_url, model=model)
    api_key = _text(resolved_cfg.get("api_key"))
    base_url = _text(resolved_cfg.get("base_url"))
    model = _text(resolved_cfg.get("model"))

    out: List[JsonDict] = []
    calls = 0
    cdir = _cache_dir()
    for raw in items or []:
        item = dict(raw)
        if item.get("llm_call_enabled") is not True:
            out.append(item)
            continue
        cache_name = str(item.get("llm_cache_key") or "").replace(":", "_") + ".json"
        cache_path = cdir / cache_name
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict):
                    cache_ready = _cache_result_is_stage_e_ready(
                        cached,
                        prompt_name=_text(item.get("prompt_name")),
                        request_type=_text(item.get("request_type")),
                    )
                    if cache_ready.get("ready"):
                        item.update(cached)
                        item["llm_result_source"] = "cache"
                        item["llm_cache_quality"] = {"status": "valid_for_stage_e", **cache_ready}
                        out.append(item)
                        continue
                    # Invalid/stale cache must not suppress a requested live call.
                    item["llm_cache_quality"] = {"status": "stale_or_incomplete", **cache_ready}
            except Exception as exc:
                item["llm_cache_quality"] = {"status": "read_failed", "error": str(exc)}
        if calls >= max_live_calls or not (api_key and model and call_text_chat_completion):
            item["llm_result"] = {}
            reason = "live_budget_exhausted" if calls >= max_live_calls else "live_config_missing"
            item["llm_result_quality"] = {
                "status": "skipped",
                "reason": reason,
                "config_ready": bool(api_key and model),
                "model": model,
                "has_base_url": bool(base_url),
            }
            item["llm_result_source"] = "skipped"
            out.append(item)
            continue
        prompt = _build_llm_prompt(item)
        try:
            raw_text = call_text_chat_completion(
                prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_prompt="你是严格、保守的中文影视剧情理解助手。",
                temperature=0.2,
                timeout=timeout,
                log_label="Stage-D 剧情理解抽样 LLM",
            )
        except Exception as exc:
            raw_text = ""
            item["llm_result_quality"] = {
                "status": "failed",
                "reason": "call_exception",
                "error": str(exc),
                "config_ready": bool(api_key and model),
                "model": model,
                "has_base_url": bool(base_url),
            }
            item["llm_result_source"] = "failed"
            item["llm_result"] = {}
            item["llm_raw_response"] = ""
            out.append(item)
            calls += 1
            continue
        calls += 1
        result = _parse_json_obj(raw_text)
        expected = item.get("quality_targets") or []
        present = [k for k in expected if _has_value(result.get(k))]
        missing = [k for k in expected if k not in present]
        if not raw_text:
            quality = {
                "status": "failed",
                "reason": "empty_response",
                "present": [],
                "missing": list(expected),
                "raw_chars": 0,
                "config_ready": bool(api_key and model),
                "model": model,
                "has_base_url": bool(base_url),
            }
            source = "failed"
        elif not result:
            quality = {
                "status": "failed",
                "reason": "json_parse_failed",
                "present": [],
                "missing": list(expected),
                "raw_chars": len(raw_text or ""),
                "raw_preview": (raw_text or "")[:500],
                "config_ready": bool(api_key and model),
                "model": model,
                "has_base_url": bool(base_url),
            }
            source = "failed"
        else:
            quality = {"status": "pass" if not missing else "review", "present": present, "missing": missing, "raw_chars": len(raw_text or ""), "config_ready": bool(api_key and model), "model": model, "has_base_url": bool(base_url)}
            source = "live"
        item.update({"llm_result": result, "llm_raw_response": (raw_text or "")[:4000], "llm_result_quality": quality, "llm_result_source": source})
        if result:
            try:
                cache_path.write_text(json.dumps({k: item[k] for k in ["llm_result", "llm_raw_response", "llm_result_quality", "llm_result_source"] if k in item}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        out.append(item)
    return out


__all__ = [
    "STAGE_D_STAGE_NAME",
    "STAGE_D_REQUIRED_ITEM_FIELDS",
    "STAGE_D_REQUIRED_PAYLOAD_FIELDS",
    "STAGE_D_GLOBAL_TARGET_FIELDS",
    "STAGE_D_LOCAL_TARGET_FIELDS",
    "build_stage_d_understanding_items",
    "evaluate_stage_d_items",
    "score_stage_d_item",
    "maybe_run_live_understanding_samples",
    "resolve_stage_d_llm_config",
]
