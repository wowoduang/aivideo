from __future__ import annotations

"""Legacy Movie Story understanding baseline adapter.

This module intentionally does not add a new product layer. It gathers the
old subtitle-first understanding chain behind one narrow boundary so the native
Movie Story engine can run the mature understanding path first, then let newer
audit/review/narration tooling consume its outputs.
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.evidence_fuser import fuse_scene_evidence
from app.services.plot_understanding_clean import (
    add_local_understanding,
    build_full_subtitle_understanding,
    build_global_summary,
    plan_story_highlights,
)
from app.services.story_validator_clean import validate_story_segments
from app.services.movie_story.evidence_enrichment import build_global_story_context, enrich_evidence_items
from app.services.movie_story.highlight_runtime import _extract_story_highlights, _select_final_story_evidence
from app.services.movie_story.legacy_segment_understanding import enrich_legacy_segment_understanding
from app.services.movie_story.story_window import _apply_llm_highlight_plan


def _has_real_llm(api_key: str, model: str) -> bool:
    return bool(str(api_key or "").strip()) and bool(str(model or "").strip())


def _ids(values: Any) -> set[str]:
    return {str(x).strip() for x in (values or []) if str(x or "").strip()}


def _time(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _overlaps_window(item: Dict[str, Any], window: Dict[str, Any], tolerance: float = 1.0) -> bool:
    start = _time(item.get("start", item.get("video_start", 0.0)))
    end = _time(item.get("end", item.get("video_end", start)))
    left = _time(window.get("start"))
    right = _time(window.get("end"), left)
    return max(start, left) <= min(end, right) + tolerance


def _highlight_windows(full_subtitle_understanding: Dict[str, Any], llm_highlight_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    windows: List[Dict[str, Any]] = []
    for source in (llm_highlight_plan or {}, full_subtitle_understanding or {}):
        for key in ("must_keep_ranges", "highlight_windows"):
            for item in source.get(key) or []:
                if isinstance(item, dict):
                    windows.append(item)
    return windows


def build_legacy_full_subtitle_understanding(
    *,
    subtitle_segments: List[Dict[str, Any]],
    api_key: str,
    base_url: str,
    model: str,
    scene_overrides: Dict[str, Any],
    resolve_prologue: Callable[..., Tuple[Dict[str, Any], List[str]]],
    resolve_tail: Callable[..., Tuple[Dict[str, Any], List[str]]],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Run the old whole-subtitle understanding stage with real LLM by default."""

    full = build_full_subtitle_understanding(
        subtitle_segments,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    full, prologue_warnings = resolve_prologue(
        full_subtitle_understanding=full,
        subtitle_segments=subtitle_segments,
        scene_overrides=scene_overrides,
    )
    full, tail_warnings = resolve_tail(
        full_subtitle_understanding=full,
        subtitle_segments=subtitle_segments,
    )
    return full, list(prologue_warnings or []), list(tail_warnings or [])


def run_legacy_understanding_chain(
    *,
    plot_chunks: List[Dict[str, Any]],
    frame_records: List[Dict[str, Any]],
    full_subtitle_understanding: Dict[str, Any],
    api_key: str,
    base_url: str,
    model: str,
    video_title: str,
    target_minutes: int,
    narrative_strategy: str,
    accuracy_priority: str,
) -> Dict[str, Any]:
    """Run old Movie Story deep understanding before newer selection tooling."""

    global_story_understanding = build_global_summary(
        plot_chunks,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    global_story_understanding.update(
        {
            "target_duration_minutes": target_minutes,
            "narrative_strategy": narrative_strategy,
            "accuracy_priority": accuracy_priority,
            "video_title": video_title,
            "full_subtitle_understanding": full_subtitle_understanding,
        }
    )
    global_story_understanding = build_global_story_context(
        plot_chunks=plot_chunks,
        full_subtitle_understanding=full_subtitle_understanding,
        existing_global_summary=global_story_understanding,
        video_title=video_title,
    )

    scene_evidence = fuse_scene_evidence(
        scenes=plot_chunks,
        frame_records=frame_records,
        visual_observations={},
    )
    for item in scene_evidence:
        item["_global_summary"] = global_story_understanding

    scene_evidence = add_local_understanding(
        scene_evidence,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    scene_evidence = enrich_evidence_items(scene_evidence, global_story_understanding)
    scene_evidence = enrich_legacy_segment_understanding(scene_evidence)

    scene_evidence = validate_story_segments(
        scene_evidence,
        global_summary=global_story_understanding,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    scene_evidence = enrich_evidence_items(scene_evidence, global_story_understanding)
    scene_evidence = enrich_legacy_segment_understanding(scene_evidence)

    llm_highlight_plan = plan_story_highlights(
        scene_evidence,
        global_summary=global_story_understanding,
        full_subtitle_summary=full_subtitle_understanding,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    scene_evidence = _apply_llm_highlight_plan(scene_evidence, full_subtitle_understanding, llm_highlight_plan)
    scene_evidence = _select_final_story_evidence(scene_evidence)

    return {
        "full_subtitle_understanding": full_subtitle_understanding,
        "global_story_understanding": global_story_understanding,
        "global_summary": global_story_understanding,
        "segment_local_understanding": [x.get("local_understanding") for x in scene_evidence if x.get("local_understanding")],
        "story_validation": [x.get("story_validation") for x in scene_evidence if x.get("story_validation")],
        "llm_highlight_plan": llm_highlight_plan,
        "scene_evidence": scene_evidence,
    }


def select_story_highlights_with_legacy_priority(
    *,
    scene_evidence: List[Dict[str, Any]],
    scene_cut_points: List[float],
    highlight_selectivity: str,
    full_subtitle_understanding: Dict[str, Any],
    llm_highlight_plan: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Prefer old LLM highlight planning; typed selection is only a backup."""

    selected_ids = _ids((llm_highlight_plan or {}).get("selected_segment_ids"))
    rejected_ids = _ids((llm_highlight_plan or {}).get("rejected_segment_ids"))
    windows = _highlight_windows(full_subtitle_understanding, llm_highlight_plan)

    llm_pool: List[Dict[str, Any]] = []
    for item in scene_evidence or []:
        seg_id = str(item.get("segment_id") or item.get("scene_id") or item.get("candidate_id") or "").strip()
        if seg_id and seg_id in rejected_ids:
            continue
        window_hit = any(_overlaps_window(item, window) for window in windows)
        if item.get("llm_highlight_selected") or (seg_id and seg_id in selected_ids) or window_hit:
            llm_pool.append(dict(item))

    if llm_pool:
        highlights = _extract_story_highlights(
            llm_pool,
            scene_cut_points,
            highlight_selectivity=highlight_selectivity,
        )
        if highlights:
            return highlights, {
                "selection_source": "legacy_llm_highlight_plan",
                "llm_pool_count": len(llm_pool),
                "typed_backup_used": False,
            }

    highlights = _extract_story_highlights(
        scene_evidence,
        scene_cut_points,
        highlight_selectivity=highlight_selectivity,
    )
    return highlights, {
        "selection_source": "typed_highlight_backup",
        "llm_pool_count": len(llm_pool),
        "typed_backup_used": True,
    }


def build_understanding_baseline_report(
    *,
    has_llm: bool,
    strategy: str = "legacy_understanding",
    full_subtitle_understanding: Dict[str, Any],
    global_story_understanding: Dict[str, Any],
    scene_evidence: List[Dict[str, Any]],
    llm_highlight_plan: Dict[str, Any],
    story_highlights: List[Dict[str, Any]],
    narration_script: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strategy = str(strategy or "legacy_understanding").strip().lower().replace("-", "_")
    segment_count = len(scene_evidence or [])
    local_count = sum(1 for x in scene_evidence or [] if x.get("local_understanding"))
    validation_count = sum(1 for x in scene_evidence or [] if x.get("story_validation"))
    highlight_signals = (
        len((full_subtitle_understanding or {}).get("highlight_windows") or [])
        + len((llm_highlight_plan or {}).get("selected_segment_ids") or [])
        + len(story_highlights or [])
    )
    counts = {
        "scene_evidence": segment_count,
        "segment_local_understanding": local_count,
        "story_validation": validation_count,
        "full_subtitle_highlight_windows": len((full_subtitle_understanding or {}).get("highlight_windows") or []),
        "llm_selected_segment_ids": len((llm_highlight_plan or {}).get("selected_segment_ids") or []),
        "story_highlights": len(story_highlights or []),
        "narration_script": len(narration_script or []),
    }
    if strategy != "legacy_understanding":
        return {
            "report": "understanding_baseline_report",
            "pipeline": "native_movie_story_runtime",
            "movie_story_strategy": strategy,
            "status": "not_applicable",
            "passed": None,
            "checks": {},
            "issues": [],
            "counts": counts,
        }

    checks = {
        "llm_configured": bool(has_llm),
        "full_subtitle_understanding": bool(full_subtitle_understanding)
        and (
            str((full_subtitle_understanding or {}).get("subtitle_understanding_status") or "").strip() not in {"", "parse_failed"}
            or bool((full_subtitle_understanding or {}).get("highlight_windows"))
            or bool((full_subtitle_understanding or {}).get("subtitle_chunk_summaries"))
            or bool((full_subtitle_understanding or {}).get("subtitle_timeline_digest"))
        ),
        "global_story_understanding": bool(global_story_understanding)
        and bool(
            (global_story_understanding or {}).get("main_storyline")
            or (global_story_understanding or {}).get("timeline_progression")
            or (global_story_understanding or {}).get("main_conflict")
        ),
        "segment_local_understanding": segment_count > 0 and local_count == segment_count,
        "story_validation": segment_count > 0 and validation_count == segment_count,
        "llm_highlight_plan": highlight_signals > 0,
        "scene_evidence": segment_count > 0,
        "narration_script": bool(narration_script),
    }
    issues = [name for name, ok in checks.items() if not ok]
    return {
        "report": "understanding_baseline_report",
        "pipeline": "legacy_movie_story_understanding_first",
        "movie_story_strategy": strategy,
        "status": "passed" if not issues else "failed",
        "passed": not issues,
        "checks": checks,
        "issues": issues,
        "counts": counts,
    }


def write_understanding_baseline_report(output_script_path: str, report: Dict[str, Any]) -> str:
    base = output_script_path.replace(".json", "_understanding_baseline_report.json")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return base


def _compact_scene_understanding(item: Dict[str, Any]) -> Dict[str, Any]:
    local = dict(item.get("local_understanding") or {})
    return {
        "segment_id": item.get("segment_id"),
        "scene_id": item.get("scene_id"),
        "timestamp": item.get("timestamp"),
        "start": item.get("start"),
        "end": item.get("end"),
        "duration": item.get("duration"),
        "subtitle_text": item.get("subtitle_text") or item.get("main_text_evidence") or "",
        "surface_dialogue_meaning": item.get("surface_dialogue_meaning") or local.get("surface_dialogue_meaning"),
        "real_narrative_state": item.get("real_narrative_state") or local.get("real_narrative_state"),
        "plot_function": item.get("plot_function") or local.get("plot_function"),
        "importance_level": item.get("importance_level") or local.get("importance_level"),
        "emotion_hint": item.get("emotion_hint") or local.get("emotion"),
        "local_understanding": local,
        "legacy_segment_understanding": item.get("legacy_segment_understanding") or local.get("legacy_segment_understanding") or {},
        "story_validation": item.get("story_validation") or {},
        "llm_highlight_selected": bool(item.get("llm_highlight_selected")),
        "llm_window_selected": bool(item.get("llm_window_selected")),
        "llm_raw_voice_keep": bool(item.get("llm_raw_voice_keep")),
        "narration_intent": item.get("narration_intent") or {},
        "evidence_completeness": item.get("evidence_completeness") or {},
        "frame_paths": list(item.get("frame_paths") or []),
        "visual_summary": list(item.get("visual_summary") or []),
    }


def _compact_narration_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "_id": item.get("_id"),
        "segment_id": item.get("segment_id"),
        "scene_id": item.get("scene_id"),
        "highlight_id": item.get("highlight_id"),
        "timestamp": item.get("timestamp"),
        "start": item.get("start"),
        "end": item.get("end"),
        "duration": item.get("duration"),
        "picture": item.get("picture"),
        "narration": item.get("narration"),
        "OST": item.get("OST"),
        "plot_function": item.get("plot_function"),
        "importance_level": item.get("importance_level"),
        "validator_status": item.get("validator_status"),
        "narration_validation": item.get("narration_validation") or {},
        "movie_story_validation": item.get("movie_story_validation") or {},
        "evidence_refs": list(item.get("evidence_refs") or []),
        "main_text_evidence": item.get("main_text_evidence") or "",
    }


def build_understanding_script_payload(
    *,
    strategy: str,
    full_subtitle_understanding: Dict[str, Any],
    global_story_understanding: Dict[str, Any],
    scene_evidence: List[Dict[str, Any]],
    story_highlights: List[Dict[str, Any]],
    llm_highlight_plan: Dict[str, Any],
    narration_script: List[Dict[str, Any]],
    understanding_baseline_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the pre-composition understanding script artifact.

    The renderer keeps consuming the lean script JSON. This richer JSON is the
    old-style inspection and organization artifact: whole-story understanding,
    every segment's understanding, highlight plan and final narration together.
    """

    return {
        "artifact": "movie_story_understanding_script",
        "movie_story_strategy": strategy,
        "pipeline": (
            "legacy_movie_story_understanding_first"
            if str(strategy or "").strip() == "legacy_understanding"
            else "native_movie_story_runtime"
        ),
        "full_subtitle_understanding": full_subtitle_understanding or {},
        "global_story_understanding": global_story_understanding or {},
        "segment_understandings": [_compact_scene_understanding(x) for x in scene_evidence or []],
        "story_validation": [x.get("story_validation") for x in scene_evidence or [] if x.get("story_validation")],
        "llm_highlight_plan": llm_highlight_plan or {},
        "story_highlights": list(story_highlights or []),
        "narration_script": [_compact_narration_item(x) for x in narration_script or []],
        "understanding_baseline_report": understanding_baseline_report or {},
        "counts": {
            "segments": len(scene_evidence or []),
            "segment_understandings": sum(1 for x in scene_evidence or [] if x.get("local_understanding")),
            "story_validation": sum(1 for x in scene_evidence or [] if x.get("story_validation")),
            "story_highlights": len(story_highlights or []),
            "narration_script": len(narration_script or []),
        },
    }


def write_understanding_script(output_script_path: str, payload: Dict[str, Any]) -> str:
    base = output_script_path.replace(".json", "_understanding_script.json")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return base
