from __future__ import annotations

"""Context, adapter, and signal helpers for the highlight-edit pipeline.

Stage-L extraction target.  This module owns runtime context helpers that do not
belong in the thin pipeline orchestrator: visual mode resolution, optional AI
adapter calls, highlight-profile enrichment, audio-signal annotation, and small
selection bookkeeping helpers.

The helpers intentionally keep dependency imports inside functions where they
wrap optional subsystems.  A missing AI/profile/audio dependency should degrade
to deterministic heuristics instead of failing the whole edit pipeline.
"""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.highlight_selector import apply_audio_signal_scores


_VISUAL_SIGNAL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "off": {
        "enabled": False,
        "boundary_args": {},
        "scene_preset": {},
    },
    "auto": {
        "enabled": True,
        "boundary_args": {
            "threshold": 27.0,
            "min_scene_len": 2.0,
            "force_split_gap": 4.0,
            "micro_threshold": 2.0,
            "min_scene_duration": 1.5,
            "merge_window_sec": 2.0,
        },
        "scene_preset": {
            "scene_threshold": 27.0,
            "min_scene_len": 2.0,
            "max_scene_duration": 12.0,
            "max_gap": 1.2,
            "force_split_gap": 4.0,
            "micro_threshold": 2.0,
            "min_scene_duration": 1.5,
        },
    },
    "boost": {
        "enabled": True,
        "boundary_args": {
            "threshold": 24.5,
            "min_scene_len": 1.2,
            "force_split_gap": 3.2,
            "micro_threshold": 1.2,
            "min_scene_duration": 1.0,
            "merge_window_sec": 1.25,
        },
        "scene_preset": {
            "scene_threshold": 24.5,
            "min_scene_len": 1.2,
            "max_scene_duration": 8.5,
            "max_gap": 0.9,
            "force_split_gap": 3.2,
            "micro_threshold": 1.2,
            "min_scene_duration": 1.0,
        },
    },
}


def resolve_visual_signal_config(visual_mode: str) -> Dict[str, Any]:
    """Return normalized visual-boundary configuration for an edit run."""
    normalized = str(visual_mode or "auto").strip().lower()
    if normalized not in _VISUAL_SIGNAL_CONFIGS:
        normalized = "auto"
    config = _VISUAL_SIGNAL_CONFIGS[normalized]
    return {
        "mode": normalized,
        "enabled": bool(config.get("enabled")),
        "boundary_args": dict(config.get("boundary_args") or {}),
        "scene_preset": dict(config.get("scene_preset") or {}),
    }


def try_ai_highlight_selection(
    candidate_clips: List[Dict[str, Any]],
    *,
    target_duration_seconds: int,
    movie_title: str,
    mode: str,
    highlight_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Run optional AI highlight selection, returning a safe empty result on failure."""
    try:
        from app.services.highlight_ai import ai_select_highlight_candidates

        return ai_select_highlight_candidates(
            candidate_clips,
            target_duration_seconds=target_duration_seconds,
            movie_title=movie_title,
            mode=mode,
            highlight_profile=highlight_profile,
        )
    except Exception as exc:
        logger.warning("AI highlight selection unavailable, fallback to heuristics: {}", exc)
        return {"used_ai": False, "selected_clip_ids": [], "selection_notes": []}


def try_ai_narration_matching(
    narration_units: List[Dict[str, Any]],
    candidate_clips: List[Dict[str, Any]],
    *,
    movie_title: str,
    highlight_profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run optional AI narration matching, returning an empty list on failure."""
    try:
        from app.services.highlight_ai import ai_match_narration_units_to_candidates

        return ai_match_narration_units_to_candidates(
            narration_units,
            candidate_clips,
            movie_title=movie_title,
            highlight_profile=highlight_profile,
        )
    except Exception as exc:
        logger.warning("AI narration matching unavailable, fallback to heuristics: {}", exc)
        return []


def select_clips_by_ids(
    candidate_clips: List[Dict[str, Any]],
    clip_ids: List[str],
    *,
    raw_audio_clip_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Return candidate copies selected by id while preserving AI/raw-audio reasons."""
    if not candidate_clips or not clip_ids:
        return []

    lookup = {str(item.get("clip_id", "") or ""): dict(item) for item in candidate_clips if item.get("clip_id")}
    raw_audio_set = {str(value) for value in (raw_audio_clip_ids or []) if str(value)}
    selected: List[Dict[str, Any]] = []
    for clip_id in clip_ids:
        item = lookup.get(str(clip_id))
        if not item:
            continue
        updated = dict(item)
        updated["selection_reason"] = list(dict.fromkeys(list(updated.get("selection_reason") or []) + ["ai_selected"]))
        if str(clip_id) in raw_audio_set:
            updated["selection_reason"] = list(
                dict.fromkeys(list(updated.get("selection_reason") or []) + ["raw_audio_keep"])
            )
            updated["raw_audio_worthy"] = True
        selected.append(updated)
    return selected


def refresh_narration_matches_from_planned(
    narration_matches: List[Dict[str, Any]],
    planned_clips: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Replace matched clip payloads with their timeline-planned copies."""
    if not narration_matches or not planned_clips:
        return narration_matches

    clip_lookup = {str(item.get("clip_id", "") or ""): dict(item) for item in planned_clips if item.get("clip_id")}
    refreshed: List[Dict[str, Any]] = []
    for match in narration_matches:
        current_clip = dict(match.get("clip") or {})
        clip_id = str(match.get("clip_id", "") or current_clip.get("clip_id", "") or "")
        planned_clip = clip_lookup.get(clip_id)
        if not planned_clip:
            refreshed.append(dict(match))
            continue

        merged_clip = dict(current_clip)
        merged_clip.update(planned_clip)
        updated = dict(match)
        updated["clip"] = merged_clip
        updated["clip_group"] = [dict(merged_clip)]
        updated["clip_ids"] = [clip_id]
        updated["group_start"] = round(float(merged_clip.get("start", 0.0) or 0.0), 3)
        updated["group_end"] = round(float(merged_clip.get("end", 0.0) or 0.0), 3)
        refreshed.append(updated)
    return refreshed


def selection_duration(clips: List[Dict[str, Any]]) -> float:
    return round(sum(max(float(item.get("duration", 0.0) or 0.0), 0.0) for item in (clips or [])), 3)


def detect_highlight_capabilities() -> Dict[str, Any]:
    """Return optional highlight-profile capabilities, or an empty fallback."""
    try:
        from app.services.highlight_profile import detect_highlight_capabilities

        return detect_highlight_capabilities()
    except Exception as exc:
        logger.warning("Highlight capability detection unavailable: {}", exc)
        return {}


def resolve_highlight_profile_context(
    *,
    requested_profile: str,
    movie_title: str,
    narration_text: str,
    subtitle_segments: List[Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    candidate_clips: List[Dict[str, Any]],
    capabilities: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the user/requested highlight profile with deterministic fallback."""
    try:
        from app.services.highlight_profile import resolve_highlight_profile

        return resolve_highlight_profile(
            requested_profile=requested_profile,
            movie_title=movie_title,
            narration_text=narration_text,
            subtitle_segments=subtitle_segments,
            plot_chunks=plot_chunks,
            candidate_clips=candidate_clips,
            capabilities=capabilities,
        )
    except Exception as exc:
        logger.warning("Highlight profile resolution unavailable, fallback to general: {}", exc)
        return {
            "id": "general",
            "label": "General / Mixed",
            "source": "fallback",
            "confidence": 0.0,
            "reasons": ["fallback_general_profile"],
            "capabilities": dict(capabilities or {}),
        }


def apply_highlight_profile_context(
    candidate_clips: List[Dict[str, Any]],
    highlight_profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Apply optional profile scoring and return safe candidate copies on failure."""
    if not candidate_clips:
        return []
    try:
        from app.services.highlight_profile import apply_highlight_profile

        return apply_highlight_profile(candidate_clips, highlight_profile)
    except Exception as exc:
        logger.warning("Highlight profile application unavailable, using raw candidate scores: {}", exc)
        return [dict(item) for item in (candidate_clips or [])]


def empty_audio_signal_summary(*, reason: str = "") -> Dict[str, Any]:
    summary = {
        "audio_signal_used": False,
        "audio_signal_clip_count": 0,
        "audio_raw_candidate_count": 0,
        "audio_signal_mean": 0.0,
        "audio_peak_mean": 0.0,
    }
    if reason:
        summary["audio_signal_reason"] = reason
    return summary


def build_shared_audio_signal_context(video_path: str) -> Dict[str, Any]:
    """Build a shared audio context once per run when the optional subsystem exists."""
    try:
        from app.services.highlight_audio import build_audio_signal_context

        return build_audio_signal_context(video_path)
    except Exception as exc:
        logger.warning("Shared highlight audio analysis unavailable: {}", exc)
        return {}


def annotate_audio_signal_context(
    video_path: str,
    candidate_clips: List[Dict[str, Any]],
    *,
    audio_context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Attach audio-signal scores to candidate clips with safe fallback behavior."""
    if not candidate_clips:
        return [], empty_audio_signal_summary()

    try:
        from app.services.highlight_audio import (
            build_audio_signal_context,
            compute_audio_scores_for_clips,
            summarize_audio_scores,
        )
    except Exception as exc:
        logger.warning("Highlight audio analysis unavailable: {}", exc)
        return [dict(item) for item in candidate_clips], empty_audio_signal_summary()

    resolved_context = dict(audio_context or {}) or build_audio_signal_context(video_path)
    if not resolved_context.get("available"):
        return [dict(item) for item in candidate_clips], empty_audio_signal_summary(
            reason=str(resolved_context.get("reason", "") or "")
        )

    audio_scores = compute_audio_scores_for_clips(candidate_clips, resolved_context)
    annotated = [
        apply_audio_signal_scores(dict(item), score)
        for item, score in zip(candidate_clips, audio_scores)
    ]
    summary = summarize_audio_scores(audio_scores)
    summary["audio_signal_used"] = True
    summary["audio_signal_reason"] = "ok"
    return annotated, summary
