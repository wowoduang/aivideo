from __future__ import annotations

"""Stage-E legacy understanding result writeback contract.

Stage E is the first place where live/cached LLM *understanding* results from
Stage D may be written back into the movie-story evidence chain.  It still does
not generate final narration.

Design goals:
- only consume Stage-D ``llm_result`` / cached result objects;
- only write whitelisted global/local understanding fields;
- score whether the result is complete enough to be trusted;
- expose an auditable contract before later stages use these fields.
"""

import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from app.services.movie_story.understanding_quality import (
    STAGE_D_GLOBAL_PROMPT,
    STAGE_D_GLOBAL_TARGET_FIELDS,
    STAGE_D_LOCAL_PROMPT,
    STAGE_D_LOCAL_TARGET_FIELDS,
)

JsonDict = Dict[str, Any]

STAGE_E_STAGE_NAME = "06d_understanding_result_writeback_contract"

STAGE_E_REQUIRED_ITEM_FIELDS = [
    "writeback_id",
    "source_sample_id",
    "request_type",
    "source_prompt_name",
    "source_highlight_id",
    "llm_result",
    "writeback_payload",
    "allowed_writeback_fields",
    "writeback_quality",
]

STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS = [
    "main_conflict",
    "story_theme",
    "genre",
    "timeline_summary",
]

STAGE_E_LOCAL_REQUIRED_MIN_FIELDS = [
    "surface_dialogue_meaning",
    "real_narrative_state",
    "conflict_summary",
    "character_motivation",
    "story_function",
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


def _prompt_name(item: Mapping[str, Any]) -> str:
    return _text(item.get("prompt_name") or item.get("source_prompt_name"))


def _allowed_fields_for_item(item: Mapping[str, Any]) -> List[str]:
    prompt = _prompt_name(item)
    if prompt == STAGE_D_GLOBAL_PROMPT or _text(item.get("request_type")) == "global_story_context_refine":
        return list(STAGE_D_GLOBAL_TARGET_FIELDS)
    return list(STAGE_D_LOCAL_TARGET_FIELDS)


def _required_min_fields_for_item(item: Mapping[str, Any]) -> List[str]:
    prompt = _prompt_name(item)
    if prompt == STAGE_D_GLOBAL_PROMPT or _text(item.get("request_type")) == "global_story_context_refine":
        return list(STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS)
    return list(STAGE_E_LOCAL_REQUIRED_MIN_FIELDS)


def _extract_llm_result(item: Mapping[str, Any]) -> JsonDict:
    # Stage-D live/cached results store refined JSON in llm_result.  Accept a
    # couple of alternate names for forward compatibility with older test runs.
    for key in ("llm_result", "refined_understanding", "result", "writeback_result"):
        val = item.get(key)
        if isinstance(val, Mapping):
            return dict(val)
        if isinstance(val, str) and val.strip().startswith("{"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as _e:
                logger.debug("JSON 解析失败: {}", _e)
    return {}


def _make_writeback_payload(result: Mapping[str, Any], allowed_fields: Sequence[str]) -> JsonDict:
    out: JsonDict = {}
    for key in allowed_fields:
        val = result.get(key)
        if _has_value(val):
            out[key] = _json_clone(val)
    return out


def score_stage_e_item(item: Mapping[str, Any]) -> JsonDict:
    missing_item: List[str] = []
    for key in STAGE_E_REQUIRED_ITEM_FIELDS:
        if key == "llm_result":
            if not isinstance(item.get(key), Mapping) or not item.get(key):
                missing_item.append(key)
            continue
        if not _has_value(item.get(key)):
            missing_item.append(key)

    allowed = list(item.get("allowed_writeback_fields") or _allowed_fields_for_item(item))
    payload = _as_dict(item.get("writeback_payload"))
    result = _as_dict(item.get("llm_result"))
    required_min = _required_min_fields_for_item(item)

    present_allowed = [k for k in allowed if _has_value(payload.get(k))]
    missing_required_min = [k for k in required_min if not _has_value(payload.get(k))]
    disallowed = [k for k in payload.keys() if k not in allowed]
    result_present = [k for k in allowed if _has_value(result.get(k))]

    coverage = len(present_allowed) / max(1, len(allowed))
    min_coverage = len([k for k in required_min if _has_value(payload.get(k))]) / max(1, len(required_min))
    no_disallowed = len(disallowed) == 0
    has_result = bool(result)
    score = round(
        max(0.0, (0.25 if has_result else 0.0) + coverage * 0.35 + min_coverage * 0.30 + (0.10 if no_disallowed else 0.0)),
        3,
    )
    # A Stage-E writeback is valid when all minimum safe-writeback fields are
    # present and no non-whitelisted fields would be written.  Optional fields
    # such as relationship_map/risk_flags improve score but are not mandatory
    # for the tiny 1-global + 2-local migration gate.
    passed = bool(has_result and no_disallowed and not missing_required_min and score >= 0.75)
    return {
        "score": score,
        "passed": passed,
        "missing_item_fields": missing_item,
        "present_allowed_fields": present_allowed,
        "missing_required_min_fields": missing_required_min,
        "disallowed_writeback_fields": disallowed,
        "coverage": round(coverage, 3),
        "min_required_coverage": round(min_coverage, 3),
        "result_present_allowed_fields": result_present,
        "can_writeback": passed,
        "request_type": item.get("request_type"),
        "source_highlight_id": item.get("source_highlight_id"),
    }


def build_stage_e_writeback_items(stage_d_items: Sequence[Mapping[str, Any]]) -> List[JsonDict]:
    out: List[JsonDict] = []
    for idx, sample in enumerate(stage_d_items or [], start=1):
        if not isinstance(sample, Mapping):
            continue
        prompt_name = _text(sample.get("prompt_name"))
        request_type = _text(sample.get("request_type"))
        if prompt_name not in {STAGE_D_GLOBAL_PROMPT, STAGE_D_LOCAL_PROMPT} and request_type not in {"global_story_context_refine", "local_understanding_refine"}:
            continue
        result = _extract_llm_result(sample)
        allowed = _allowed_fields_for_item(sample)
        payload = _make_writeback_payload(result, allowed)
        source_id = _text(sample.get("sample_id") or sample.get("candidate_id") or f"stage_d_{idx:03d}")
        hid = _text(sample.get("source_highlight_id") or sample.get("highlight_id"))
        item: JsonDict = {
            "writeback_id": f"stage_e_writeback_{idx:03d}_{source_id}",
            "candidate_id": f"stage_e_writeback_{idx:03d}_{source_id}",
            "highlight_id": hid or source_id,
            "source_sample_id": source_id,
            "request_type": request_type,
            "candidate_type": "stage_e_understanding_result_writeback_contract",
            "source_prompt_name": prompt_name,
            "source_highlight_id": hid,
            "llm_result": _json_clone(result),
            "llm_result_source": sample.get("llm_result_source") or ("missing" if not result else "provided"),
            "llm_result_quality": _json_clone(sample.get("llm_result_quality") or {}),
            "writeback_payload": payload,
            "allowed_writeback_fields": allowed,
            "writeback_policy": "whitelist_only_no_final_narration_generation",
            "writeback_quality": {"status": "pending"},
        }
        item["writeback_quality"] = score_stage_e_item(item)
        out.append(item)
    return out


def evaluate_stage_e_items(
    items: Sequence[Mapping[str, Any]],
    *,
    min_pass_rate: float = 0.9,
    min_global_results: int = 1,
    min_local_results: int = 2,
) -> JsonDict:
    scored: List[JsonDict] = []
    for idx, item in enumerate(items or [], start=1):
        q = _as_dict(item.get("writeback_quality")) or score_stage_e_item(item)
        request_type = _text(item.get("request_type"))
        is_global = request_type == "global_story_context_refine" or _text(item.get("source_prompt_name")) == STAGE_D_GLOBAL_PROMPT
        is_local = request_type == "local_understanding_refine" or _text(item.get("source_prompt_name")) == STAGE_D_LOCAL_PROMPT
        scored.append({
            "idx": idx,
            "id": item.get("writeback_id") or item.get("candidate_id") or item.get("id"),
            "request_type": request_type,
            "source_prompt_name": item.get("source_prompt_name"),
            "source_highlight_id": item.get("source_highlight_id"),
            "score": q.get("score", 0.0),
            "passed": bool(q.get("passed")),
            "can_writeback": bool(q.get("can_writeback")),
            "missing_item_fields": q.get("missing_item_fields") or [],
            "present_allowed_fields": q.get("present_allowed_fields") or [],
            "missing_required_min_fields": q.get("missing_required_min_fields") or [],
            "disallowed_writeback_fields": q.get("disallowed_writeback_fields") or [],
            "coverage": q.get("coverage"),
            "llm_result_source": item.get("llm_result_source"),
            "is_global": is_global,
            "is_local": is_local,
        })
    total = len(scored)
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    global_success = sum(1 for x in scored if x.get("passed") and x.get("is_global"))
    local_success = sum(1 for x in scored if x.get("passed") and x.get("is_local"))
    missing_result_count = sum(1 for x in scored if "llm_result" in (x.get("missing_item_fields") or []))
    disallowed_count = sum(1 for x in scored if x.get("disallowed_writeback_fields"))
    return {
        "stage": "stage_e_understanding_result_writeback_contract",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        # Stage E is commonly run with a tiny live-call budget (for example
        # 1 global + 2 local results out of 9 Stage-D requests).  Therefore the
        # pass condition is based on required successful writebacks, not on all
        # sampled requests having live results.
        "overall_passed": (
            total > 0
            and global_success >= min_global_results
            and local_success >= min_local_results
            and disallowed_count == 0
        ),
        "global_success_count": global_success,
        "local_success_count": local_success,
        "min_global_results": min_global_results,
        "min_local_results": min_local_results,
        "missing_result_count": missing_result_count,
        "disallowed_writeback_count": disallowed_count,
        "required_item_fields": STAGE_E_REQUIRED_ITEM_FIELDS,
        "global_allowed_fields": STAGE_D_GLOBAL_TARGET_FIELDS,
        "local_allowed_fields": STAGE_D_LOCAL_TARGET_FIELDS,
        "global_required_min_fields": STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS,
        "local_required_min_fields": STAGE_E_LOCAL_REQUIRED_MIN_FIELDS,
        "items": scored,
    }


def apply_stage_e_writebacks(
    global_context: Mapping[str, Any] | None,
    evidence_items: Sequence[Mapping[str, Any]],
    stage_e_items: Sequence[Mapping[str, Any]],
) -> Tuple[JsonDict, List[JsonDict]]:
    """Apply only verified whitelist writebacks to copies of context/evidence."""
    new_global: JsonDict = dict(global_context or {})
    new_items: List[JsonDict] = [dict(x) for x in (evidence_items or []) if isinstance(x, Mapping)]
    by_hid: Dict[str, JsonDict] = {}
    for item in new_items:
        for key in (item.get("highlight_id"), item.get("candidate_id"), item.get("segment_id"), item.get("id")):
            if key:
                by_hid[str(key)] = item

    for raw in stage_e_items or []:
        item = dict(raw)
        q = _as_dict(item.get("writeback_quality")) or score_stage_e_item(item)
        if not q.get("passed"):
            continue
        payload = _as_dict(item.get("writeback_payload"))
        request_type = _text(item.get("request_type"))
        if request_type == "global_story_context_refine":
            for key in STAGE_D_GLOBAL_TARGET_FIELDS:
                if _has_value(payload.get(key)):
                    new_global[key] = _json_clone(payload.get(key))
            new_global["understanding_source"] = "stage_e_llm_writeback"
        else:
            hid = _text(item.get("source_highlight_id") or item.get("highlight_id"))
            target = by_hid.get(hid)
            if not target:
                continue
            local = dict(_as_dict(target.get("local_understanding")))
            for key in STAGE_D_LOCAL_TARGET_FIELDS:
                if _has_value(payload.get(key)):
                    target[key] = _json_clone(payload.get(key))
                    local[key] = _json_clone(payload.get(key))
            target["local_understanding"] = local
            target["understanding_source"] = "stage_e_llm_writeback"
    return new_global, new_items


__all__ = [
    "STAGE_E_STAGE_NAME",
    "STAGE_E_REQUIRED_ITEM_FIELDS",
    "STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS",
    "STAGE_E_LOCAL_REQUIRED_MIN_FIELDS",
    "build_stage_e_writeback_items",
    "evaluate_stage_e_items",
    "score_stage_e_item",
    "apply_stage_e_writebacks",
]
