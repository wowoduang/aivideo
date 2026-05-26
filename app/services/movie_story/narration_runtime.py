from __future__ import annotations

"""Production narration runtime for the movie-story chain.

This module is the production adapter around the existing mature narration
generator.  It owns narration LLM mode selection at execution time while keeping
the generator contract unchanged, so callers do not need to know whether a
segment was produced by batch/full/hybrid/fallback mode.
"""

from typing import Any, Dict, List

from app.services.generate_narration_script_clean import (
    generate_narration_from_scene_evidence as legacy_generate_narration_from_scene_evidence,
)
from app.services.movie_story.time_utils import coerce_time_pair
from app.utils import utils


def _looks_like_placeholder_secret(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    return normalized in {"your-api-key", "your_api_key", "sk-xxx", "sk-xxxx", "sk-test", "test", "none", "null"}


def _has_real_llm_config(api_key: str, model: str) -> bool:
    return bool(str(model or "").strip()) and not _looks_like_placeholder_secret(api_key)


def _build_disabled_migration_script_items(narration_evidence: List[Dict[str, Any]], *, video_title: str = "") -> List[Dict[str, Any]]:
    """Return placeholder script items without calling any LLM.

    Stage A verifies old-project evidence migration only.  This function keeps
    the end-to-end artifact shape available while making the token cost exactly
    zero for final narration generation.
    """
    items: List[Dict[str, Any]] = []
    for idx, ev in enumerate(narration_evidence or [], start=1):
        start, end = coerce_time_pair(
            ev.get("start", ev.get("video_start", 0.0)),
            ev.get("end", ev.get("video_end", 0.0)),
            min_duration=1.0,
        )
        timestamp = ev.get("timestamp") or f"{utils.format_time(start)}-{utils.format_time(end)}"
        items.append({
            "_id": idx,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "timestamp": timestamp,
            "segment_id": ev.get("segment_id"),
            "scene_id": ev.get("scene_id"),
            "highlight_id": ev.get("highlight_id"),
            "picture": ev.get("picture") or ev.get("visual_text") or "",
            "narration": "【流程测试占位】已跳过大模型写稿，仅用于验证字幕、分段、高光、产物保存和后续链路。",
            "OST": ev.get("OST", 2),
            "generation_mode": "llm_skipped_flow_test",
            "migration_stage": "llm_skipped_flow_test",
            "used_global_summary": bool(ev.get("_global_summary")),
            "used_local_understanding": bool(ev.get("local_understanding")),
            "used_story_function": bool(ev.get("story_function")),
            "evidence_completeness": ev.get("evidence_completeness"),
            "narration_disabled_reason": "skip_llm=true; final LLM writing is intentionally skipped to save tokens while testing the pipeline.",
            "llm_skipped": True,
        })
    return items


def _generate_narration_with_mode(
    narration_evidence: List[Dict[str, Any]],
    *,
    mode: str,
    max_llm_segments: int,
    api_key: str,
    base_url: str,
    model: str,
    style: str,
    video_title: str,
) -> List[Dict[str, Any]]:
    if not narration_evidence:
        return []
    mode = str(mode or "fallback").lower()
    if mode == "disabled":
        return _build_disabled_migration_script_items(narration_evidence, video_title=video_title)
    if mode == "fallback" or not _has_real_llm_config(api_key, model):
        return legacy_generate_narration_from_scene_evidence(
            scene_evidence=narration_evidence,
            api_key="",
            base_url="",
            model="",
            style=style or "general",
            video_title=video_title,
        )
    if mode in {"full", "batch"}:
        # Full/batch mode must use the real LLM path for every selected evidence
        # segment.  The flow hang fix is achieved by removing duplicate video
        # scanning and by bounding highlight planning, not by copying subtitles
        # into narration.
        return legacy_generate_narration_from_scene_evidence(
            scene_evidence=narration_evidence,
            api_key=api_key,
            base_url=base_url,
            model=model,
            style=style or "general",
            video_title=video_title,
        )

    # hybrid: only use LLM on the first N selected highlights; fallback for the rest
    n = max(0, int(max_llm_segments or 0))
    if n <= 0:
        return legacy_generate_narration_from_scene_evidence(
            scene_evidence=narration_evidence,
            api_key="",
            base_url="",
            model="",
            style=style or "general",
            video_title=video_title,
        )
    head = narration_evidence[:n]
    tail = narration_evidence[n:]
    items: List[Dict[str, Any]] = []
    if head:
        items.extend(legacy_generate_narration_from_scene_evidence(
            scene_evidence=head,
            api_key=api_key,
            base_url=base_url,
            model=model,
            style=style or "general",
            video_title=video_title,
        ))
    if tail:
        items.extend(legacy_generate_narration_from_scene_evidence(
            scene_evidence=tail,
            api_key="",
            base_url="",
            model="",
            style=style or "general",
            video_title=video_title,
        ))
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            item["_id"] = idx
            item["narration_llm_mode"] = mode
    return items
