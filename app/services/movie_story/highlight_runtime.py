from __future__ import annotations

"""Highlight planning and final story-evidence selection runtime.

This module owns the old AIVideoGPT highlight-planning glue that was still
embedded in ``subtitle_first_pipeline.py``: compact LLM planning input, bounded
planning fallback, typed-selector fallback, and final evidence scoring guards.
"""

import os
from typing import Any, Dict, List

from loguru import logger

from app.services.plot_understanding import plan_story_highlights
from app.services.movie_story.audit_runtime import _audit_config_value_v41, _audit_int_v41
from app.services.movie_story.runtime_options import _has_real_llm_config, _runtime_config_value, _runtime_int
from app.services.movie_story.story_runtime import (
    extract_highlights as select_typed_story_highlights,
    keep_scene_evidence as keep_authoritative_scene_evidence,
)
from app.utils import utils


def _compact_highlight_plan_summary(global_summary: Dict[str, Any], full_subtitle_understanding: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Keep LLM highlight planning real but bounded.

    Passing the full subtitle understanding back into the highlighter can create
    a very large prompt on long dramas.  The highlighter only needs storyline,
    entity hints and precomputed windows, not every raw field.
    """
    gs = dict(global_summary or {})
    fsu = dict(full_subtitle_understanding or {})
    compact_global = {
        "video_title": gs.get("video_title"),
        "protagonist": gs.get("protagonist"),
        "main_storyline": str(gs.get("main_storyline") or "")[:1200],
        "character_relations": list(gs.get("character_relations") or [])[:20],
        "core_conflicts": list(gs.get("core_conflicts") or [])[:20],
        "timeline_progression": list(gs.get("timeline_progression") or [])[:24],
        "unresolved_tensions": list(gs.get("unresolved_tensions") or [])[:16],
        "narrative_risk_flags": list(gs.get("narrative_risk_flags") or [])[:12],
        "entity_map": gs.get("entity_map") or {},
        "arc": str(gs.get("arc") or "")[:500],
    }
    compact_full = {
        "subtitle_understanding_status": fsu.get("subtitle_understanding_status"),
        "prologue_end_time": fsu.get("prologue_end_time"),
        "story_end_time": fsu.get("story_end_time"),
        "highlight_windows": list(fsu.get("highlight_windows") or [])[:40],
        "highlight_windows_source": fsu.get("highlight_windows_source"),
        "main_storyline": str(fsu.get("main_storyline") or fsu.get("summary") or "")[:1200],
        "key_events": list(fsu.get("key_events") or fsu.get("events") or [])[:40],
        "character_relations": list(fsu.get("character_relations") or [])[:20],
        "risk_flags": list(fsu.get("risk_flags") or fsu.get("narrative_risk_flags") or [])[:12],
    }
    return compact_global, compact_full


def _rank_evidence_for_highlight_plan(scene_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def score(item: Dict[str, Any]) -> float:
        value = 0.0
        try:
            value += float(item.get("final_story_score") or item.get("story_score") or item.get("highlight_score") or item.get("score") or 0.0)
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)
        if str(item.get("importance_level") or "").lower() == "high":
            value += 2.0
        if item.get("llm_window_selected"):
            value += 1.5
        if item.get("raw_voice_retain_suggestion") or item.get("llm_raw_voice_keep"):
            value += 0.8
        plot = str(item.get("plot_function") or "")
        if any(token in plot for token in ("反转", "冲突", "情感", "信息", "结局", "高潮")):
            value += 0.7
        return value

    ranked = sorted((dict(x) for x in scene_evidence or [] if isinstance(x, dict)), key=lambda x: (-score(x), float(x.get("start", 0.0) or 0.0)))
    return ranked


def _safe_plan_story_highlights(
    scene_evidence: List[Dict[str, Any]],
    *,
    global_summary: Dict[str, Any],
    full_subtitle_understanding: Dict[str, Any],
    allow_llm: bool,
    api_key: str,
    base_url: str,
    model: str,
    scene_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a strategy-scoped highlight plan.

    ``legacy_understanding`` restores the old subtitle-first highlighter as a
    full-understanding planner. ``native_runtime`` keeps the newer bounded
    candidate planning path. The two strategies share the same output contract,
    but they do not override each other's selection policy.
    """
    fallback = {
        "selected_segment_ids": [],
        "rejected_segment_ids": [],
        "raw_voice_segment_ids": [],
        "must_keep_ranges": list((full_subtitle_understanding or {}).get("highlight_windows") or []),
        "selection_notes": ["local_highlight_plan_guard"],
        "plan_policy": "local_guard_no_blocking_llm",
    }
    if not scene_evidence:
        return fallback

    disable_llm = str(
        scene_overrides.get("movie_story_disable_llm_highlight_plan")
        or os.environ.get("AIVIDEO_MOVIE_STORY_DISABLE_LLM_HIGHLIGHT_PLAN")
        or _runtime_config_value("movie_story_disable_llm_highlight_plan", "")
        or ""
    ).strip().lower() in {"1", "true", "yes", "on", "disabled", "disable"}

    if not (allow_llm and (not disable_llm) and _has_real_llm_config(api_key, model)):
        return fallback

    strategy = str(scene_overrides.get("movie_story_strategy") or "legacy_understanding").strip().lower().replace("-", "_")
    use_legacy_full_plan = strategy in {"legacy_understanding", "legacy", "old", "old_understanding", "subtitle_first", "deep_understanding"}
    max_candidates = int(
        scene_overrides.get("movie_story_highlight_plan_max_candidates")
        or _runtime_int("movie_story_highlight_plan_max_candidates", "AIVIDEO_MOVIE_STORY_HIGHLIGHT_PLAN_MAX_CANDIDATES", 32)
        or 32
    )
    max_candidates = max(8, min(max_candidates, 80))
    if use_legacy_full_plan:
        planning_evidence = list(scene_evidence or [])
        planning_global_summary = global_summary
        planning_full_summary = full_subtitle_understanding
        plan_policy = "legacy_llm_full_understanding_plan"
    else:
        planning_evidence = _rank_evidence_for_highlight_plan(scene_evidence)[:max_candidates]
        planning_global_summary, planning_full_summary = _compact_highlight_plan_summary(global_summary, full_subtitle_understanding)
        plan_policy = "native_llm_capped_ranked_compact_plan"
    try:
        plan = plan_story_highlights(
            planning_evidence,
            global_summary=planning_global_summary,
            full_subtitle_summary=planning_full_summary,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        if isinstance(plan, dict):
            plan.setdefault("plan_policy", plan_policy)
            plan.setdefault("candidate_count", len(planning_evidence))
            plan.setdefault("total_scene_evidence_count", len(scene_evidence or []))
            plan.setdefault("movie_story_strategy", "legacy_understanding" if use_legacy_full_plan else "native_runtime")
            return plan
    except Exception as exc:
        logger.exception("高光 LLM 规划失败，记录错误并继续执行 typed 选择器: {}", exc)
        fallback["plan_policy"] = "llm_failed_typed_selector_continues"
        fallback["llm_error"] = str(exc)
    return fallback


def _fallback_global_summary(plot_chunks: List[Dict[str, Any]], full_subtitle_understanding: Dict[str, Any], video_title: str = "") -> Dict[str, Any]:
    text_parts = []
    key_segments = []
    for idx, item in enumerate(plot_chunks[:24], start=1):
        text = str(item.get("aligned_subtitle_text") or item.get("subtitle_text") or item.get("main_text_evidence") or item.get("text") or "").strip()
        if text:
            text_parts.append(text[:80])
        if idx <= 8:
            key_segments.append(item.get("segment_id") or item.get("scene_id") or item.get("id") or f"seg_{idx:03d}")
    return {
        "protagonist": "主角",
        "main_storyline": "；".join(text_parts[:8])[:500],
        "character_relations": [],
        "core_conflicts": [],
        "timeline_progression": text_parts[:12],
        "unresolved_tensions": [],
        "narrative_risk_flags": ["fallback_global_summary"],
        "entity_map": {},
        "arc": "fallback",
        "key_segments": key_segments,
        "video_title": video_title,
        "full_subtitle_understanding": full_subtitle_understanding or {},
    }


def _build_story_candidates_from_evidence(scene_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        if not isinstance(item, dict):
            continue
        start = item.get("start", item.get("video_start", 0.0))
        end = item.get("end", item.get("video_end", start))
        out.append({
            "candidate_id": item.get("candidate_id") or item.get("segment_id") or item.get("scene_id") or f"story_{idx:04d}",
            "segment_id": item.get("segment_id"),
            "scene_id": item.get("scene_id"),
            "start": start,
            "end": end,
            "timestamp": item.get("timestamp") or f"{utils.format_time(float(start or 0.0))}-{utils.format_time(float(end or 0.0))}",
            "plot_function": item.get("plot_function"),
            "importance_level": item.get("importance_level"),
            "score": item.get("final_story_score") or item.get("story_score") or item.get("score") or 0,
            "text": str(item.get("subtitle_text") or item.get("main_text_evidence") or item.get("text") or "")[:260],
            "validator_status": (item.get("story_validation") or {}).get("validator_status", "pass") if isinstance(item.get("story_validation"), dict) else "pass",
            "raw_voice_retain_suggestion": bool(item.get("raw_voice_retain_suggestion")),
        })
    return out


def _merge_highlight_segments(highlights: List[Dict[str, Any]], gap_threshold: float = 1.2) -> List[Dict[str, Any]]:
    """合并相邻或重叠的高光候选片段。
    
    这是时间区间合并 helper，目标是减少重复候选并保持剪辑窗口连续。
    """
    if not highlights:
        return []

    ordered = sorted(highlights, key=lambda x: (float(x.get("start", 0.0) or 0.0), -float(x.get("highlight_score", 0.0) or 0.0)))
    merged: List[Dict[str, Any]] = [dict(ordered[0])]
    for item in ordered[1:]:
        current = dict(item)
        prev = merged[-1]
        prev_end = float(prev.get("end", 0.0) or 0.0)
        current_start = float(current.get("start", 0.0) or 0.0)
        overlaps = current_start <= prev_end + gap_threshold
        if not overlaps:
            merged.append(current)
            continue

        prev["start"] = round(min(float(prev.get("start", 0.0) or 0.0), current_start), 3)
        prev["end"] = round(max(prev_end, float(current.get("end", prev_end) or prev_end)), 3)
        prev["semantic_start"] = round(min(float(prev.get("semantic_start", prev["start"]) or prev["start"]), float(current.get("semantic_start", current_start) or current_start)), 3)
        prev["semantic_end"] = round(max(float(prev.get("semantic_end", prev["end"]) or prev["end"]), float(current.get("semantic_end", prev["end"]) or prev["end"])), 3)
        prev["duration"] = round(max(float(prev["end"]) - float(prev["start"]), 0.1), 3)
        prev["semantic_duration"] = round(max(float(prev["semantic_end"]) - float(prev["semantic_start"]), 0.1), 3)
        prev["highlight_score"] = round(max(float(prev.get("highlight_score", 0.0) or 0.0), float(current.get("highlight_score", 0.0) or 0.0)), 3)
        prev["plot_functions"] = sorted({*(prev.get("plot_functions") or []), *(current.get("plot_functions") or [])})
        prev["scene_ids"] = sorted({*(prev.get("scene_ids") or []), *(current.get("scene_ids") or [])})
        prev["segment_ids"] = sorted({*(prev.get("segment_ids") or []), *(current.get("segment_ids") or [])})
        prev["evidence_ids"] = sorted({*(prev.get("evidence_ids") or []), *(current.get("evidence_ids") or [])})
        prev["highlight_reasons"] = sorted({*(prev.get("highlight_reasons") or []), *(current.get("highlight_reasons") or [])})
        prev["raw_voice_retain"] = bool(prev.get("raw_voice_retain") or current.get("raw_voice_retain"))
        left_story_end = prev.get("story_end")
        right_story_end = current.get("story_end")
        if left_story_end is None:
            prev["story_end"] = right_story_end
        elif right_story_end is None:
            prev["story_end"] = left_story_end
        else:
            prev["story_end"] = round(min(float(left_story_end), float(right_story_end)), 3)
        prev["story_end_trimmed"] = bool(prev.get("story_end_trimmed") or current.get("story_end_trimmed"))
        prev["story_end_original_after_story_end"] = bool(
            prev.get("story_end_original_after_story_end") or current.get("story_end_original_after_story_end")
        )
        prev["after_story_end"] = bool(prev.get("after_story_end") or current.get("after_story_end"))
        prev["boundary_confidence"] = "high" if "high" in {str(prev.get("boundary_confidence") or ""), str(current.get("boundary_confidence") or "")} else str(prev.get("boundary_confidence") or current.get("boundary_confidence") or "medium")
        prev["timestamp"] = f"{utils.format_time(float(prev['start']))}-{utils.format_time(float(prev['end']))}"
        prev["semantic_timestamp"] = f"{utils.format_time(float(prev['semantic_start']))}-{utils.format_time(float(prev['semantic_end']))}"

    for idx, item in enumerate(merged, start=1):
        item["highlight_id"] = f"highlight_{idx:03d}"
        item["highlight_rank"] = idx
    return merged


def _movie_story_runtime_highlight_selectivity(requested="balanced"):
    import os
    value = (
        os.environ.get("AIVIDEO_HIGHLIGHT_SELECTIVITY")
        or os.environ.get("MOVIE_STORY_HIGHLIGHT_SELECTIVITY")
        or ""
    ).strip()
    if not value:
        value = str(_audit_config_value_v41("movie_story_highlight_selectivity", "") or _audit_config_value_v41("highlight_selectivity", "") or "").strip()
    value = (value or requested or "balanced").strip().lower()
    aliases = {"宽松": "loose", "较宽松": "loose", "很宽松": "very_loose", "严格": "strict", "均衡": "balanced", "默认": "balanced", "normal": "balanced", "medium": "balanced"}
    value = aliases.get(value, value)
    if value not in {"strict", "balanced", "loose", "very_loose"}:
        value = "balanced"
    logger.warning("高光严格度: {}", value)
    return value


def _extract_story_highlights(scene_evidence, cut_points=None, highlight_selectivity="loose", *args, **kwargs):
    selected = select_typed_story_highlights(scene_evidence, cut_points=cut_points, highlight_selectivity=highlight_selectivity, *args, **kwargs)
    if selected:
        return selected
    # Compatibility fallback for lightweight tests and degraded runtime: do not
    # restore prologue/tail, but keep obvious high-value or loose-mode evidence.
    threshold = {"strict": 2.5, "balanced": 2.0, "loose": 0.8, "very_loose": 0.2}.get(str(highlight_selectivity or "balanced"), 2.0)
    out = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        if not isinstance(item, dict) or item.get("before_prologue_end") or item.get("after_story_end"):
            continue
        score = float(item.get("final_story_score", item.get("highlight_score", item.get("score", 0.0))) or 0.0)
        keep = score >= threshold or bool(item.get("llm_highlight_selected"))
        if not keep:
            continue
        row = dict(item)
        row.setdefault("highlight_id", row.get("scene_id") or row.get("segment_id") or f"highlight_{idx:03d}")
        row.setdefault("highlight_rank", len(out) + 1)
        row.setdefault("segment_ids", [row.get("segment_id") or row.get("highlight_id")])
        row.setdefault("scene_ids", [row.get("scene_id") or row.get("highlight_id")])
        row.setdefault("evidence_ids", [row.get("segment_id") or row.get("scene_id") or row.get("highlight_id")])
        if row.get("story_end_trimmed") and row.get("story_end") is not None:
            try:
                row["end"] = min(float(row.get("end", row.get("story_end")) or 0.0), float(row.get("story_end") or 0.0))
            except Exception as _e:
                logger.debug("story_end 修正失败: {}", _e)
        out.append(row)
    return out


def _resolve_highlight_selectivity(value: str) -> str:
    normalized = str(value or "balanced").strip().lower()
    aliases = {
        "宽松": "loose",
        "较宽松": "loose",
        "很宽松": "very_loose",
        "严格": "strict",
        "均衡": "balanced",
        "默认": "balanced",
        "normal": "balanced",
        "medium": "balanced",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"very_loose", "loose", "balanced", "strict"}:
        return normalized
    return "balanced"


def _final_story_score(pkg: Dict, index: int, total: int) -> float:
    """计算候选片段的最终故事价值分数。
    
    该分数服务长视频拆短视频候选排序；不要在这里恢复旧 subtitle-first 理解链。
    """
    score = 0.0
    importance = str(pkg.get("importance_level") or "medium")
    plot_function = str(pkg.get("plot_function") or "")
    block_type = str(pkg.get("block_type") or "dialogue")
    boundary_confidence = str(pkg.get("boundary_confidence") or "medium")
    validator = pkg.get("story_validation") or {}
    validator_status = str(validator.get("validator_status") or "pass")
    duration = max(float(pkg.get("end", 0.0) or 0.0) - float(pkg.get("start", 0.0) or 0.0), 0.0)
    text = str(pkg.get("subtitle_text") or pkg.get("main_text_evidence") or "")

    if importance == "high":
        score += 3.0
    elif importance == "medium":
        score += 1.4
    else:
        score -= 0.8

    if plot_function in {"\u53cd\u8f6c", "\u60c5\u611f\u7206\u53d1", "\u7ed3\u5c40\u6536\u675f", "\u51b2\u7a81\u5347\u7ea7"}:
        score += 1.8
    elif plot_function in {"\u4fe1\u606f\u63ed\u9732"}:
        score += 0.8
    elif plot_function in {"\u94fa\u57ab", "\u8282\u594f\u7f13\u51b2"}:
        score -= 1.0

    if block_type in {"action", "emotion", "visual"}:
        score += 0.8
    elif block_type == "transition":
        score -= 1.0

    if boundary_confidence == "high":
        score += 0.5
    elif boundary_confidence == "low":
        score -= 0.8

    if validator_status == "pass":
        score += 0.4
    elif validator_status == "review":
        score -= 0.3
    elif validator_status == "risky":
        score -= 1.2

    if pkg.get("raw_voice_retain_suggestion"):
        score += 0.5
    if pkg.get("need_visual_verify"):
        score += 0.2
    if pkg.get("llm_highlight_selected"):
        score += 2.2
    if pkg.get("llm_highlight_rejected"):
        score -= 2.5
    if pkg.get("llm_raw_voice_keep"):
        score += 0.8
    if pkg.get("before_prologue_end") and not pkg.get("llm_highlight_selected"):
        score -= 2.0
    if pkg.get("after_story_end"):
        score -= 3.0

    if duration >= 40.0:
        score -= 0.6
    elif 4.0 <= duration <= 24.0:
        score += 0.3

    if len(text.strip()) < 10:
        score -= 0.5
    if index <= max(1, int(total * 0.12)) and plot_function == "\u94fa\u57ab":
        score -= 1.5

    return round(score, 3)


def _select_final_story_evidence(scene_evidence):
    """Keep final story evidence while guarding against prologue/tail leakage.

    The authoritative selector lives in movie_story.story_runtime.  This wrapper
    stays for old imports/tests and adds a hard compatibility guard so a unit-test
    stub of keep_scene_evidence cannot accidentally restore trimmed prologue rows.
    """
    selected = keep_authoritative_scene_evidence(scene_evidence)
    rows = [dict(x) for x in (selected or []) if isinstance(x, dict)]
    guarded = [x for x in rows if not x.get("before_prologue_end") and not x.get("after_story_end")]
    if guarded:
        return guarded
    return [dict(x) for x in (scene_evidence or []) if isinstance(x, dict) and not x.get("before_prologue_end") and not x.get("after_story_end")]
