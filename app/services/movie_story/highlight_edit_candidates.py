from __future__ import annotations

"""Candidate builders for the highlight-edit pipeline.

Stage-K extraction target.  This module owns conversion from subtitle/plot/scene
signals into reusable candidate clips, plus narrated-mode candidate pools.  It is
pure pipeline logic: no file I/O, no progress callbacks, no LLM calls.
"""

from typing import Any, Dict, List

from app.services.highlight_selector import (
    build_candidate_from_plot_chunk,
    enrich_candidate_evidence,
    select_highlight_clips,
)
from app.services.movie_story import highlight_edit_selection as movie_story_edit_selection


def _build_coverage_clips(candidate_clips: List[Dict[str, Any]], desired_count: int) -> List[Dict[str, Any]]:
    """Compatibility helper used by the narrated pool builder."""
    pool = movie_story_edit_selection.build_highlight_recut_selection_pool(
        candidate_clips,
        max(int(desired_count or 1) * 35, 35),
        select_highlight_fn=select_highlight_clips,
    )
    return [clip for clip in pool if "coverage_anchor" in set(clip.get("selection_reason") or [])][: max(int(desired_count or 0), 1)]

def _build_candidate_clips(
    *,
    plot_chunks: List[Dict[str, Any]],
    scene_segments: List[Dict[str, Any]],
    subtitle_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    total_plot_chunks = len(plot_chunks or [])
    subtitle_segment_map = _build_subtitle_segment_map(subtitle_segments)

    for idx, chunk in enumerate(plot_chunks or [], start=1):
        candidates.append(build_candidate_from_plot_chunk(chunk, idx, total_plot_chunks))

    if candidates:
        return candidates

    for idx, scene in enumerate(scene_segments or [], start=1):
        start = float(scene.get("start", 0.0) or 0.0)
        end = float(scene.get("end", start) or start)
        if end <= start:
            end = start + 0.5
        story_position = round((idx - 1) / max(len(scene_segments or []) - 1, 1), 3) if len(scene_segments or []) > 1 else 0.5
        dialogue_signals = _collect_scene_dialogue_signals(scene, subtitle_segment_map)
        candidates.append(
            enrich_candidate_evidence(
                {
                "clip_id": f"scene_clip_{idx:04d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "source": "scene",
                "story_index": idx,
                "story_position": story_position,
                "story_stage_hint": "opening" if story_position <= 0.12 else "ending" if story_position >= 0.88 else "setup",
                "plot_function": "",
                "plot_role": "",
                "character_names": [],
                "subtitle_text": "",
                "scene_summary": "",
                "energy_score": 0.45,
                "story_score": 0.35,
                "emotion_score": 0.35,
                "total_score": 0.38,
                "raw_audio_worthy": True,
                "tags": ["scene_fallback"],
                "source_scene_id": str(scene.get("scene_id", "") or ""),
                "source_segment_ids": list(scene.get("subtitle_ids") or []),
                "speaker_sequence": list(dialogue_signals["speaker_sequence"]),
                "speaker_names": list(dialogue_signals["speaker_names"]),
                "speaker_turns": int(dialogue_signals["speaker_turns"]),
                "exchange_pairs": list(dialogue_signals["exchange_pairs"]),
                "selection_reason": ["scene_fallback"],
                }
            )
        )
    return candidates

def _scene_overlap_seconds(scene: Dict[str, Any], chunk: Dict[str, Any]) -> float:
    scene_start = float(scene.get("start", 0.0) or 0.0)
    scene_end = float(scene.get("end", scene_start) or scene_start)
    chunk_start = float(chunk.get("start", 0.0) or 0.0)
    chunk_end = float(chunk.get("end", chunk_start) or chunk_start)
    return max(0.0, min(scene_end, chunk_end) - max(scene_start, chunk_start))

def _scene_center_distance(scene: Dict[str, Any], chunk: Dict[str, Any]) -> float:
    scene_start = float(scene.get("start", 0.0) or 0.0)
    scene_end = float(scene.get("end", scene_start) or scene_start)
    chunk_start = float(chunk.get("start", 0.0) or 0.0)
    chunk_end = float(chunk.get("end", chunk_start) or chunk_start)
    scene_center = (scene_start + scene_end) / 2.0
    chunk_center = (chunk_start + chunk_end) / 2.0
    return abs(scene_center - chunk_center)

def _find_best_plot_chunk_for_scene(scene: Dict[str, Any], plot_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not plot_chunks:
        return {}

    best = None
    best_key = None
    for chunk in plot_chunks:
        overlap = _scene_overlap_seconds(scene, chunk)
        distance = _scene_center_distance(scene, chunk)
        highlight_score = float(chunk.get("highlight_score", 0.0) or 0.0)
        key = (overlap, -distance, highlight_score)
        if best is None or key > best_key:
            best = chunk
            best_key = key

    if best is None:
        return {}
    if float(best_key[0]) > 0.0 or float(-best_key[1]) <= 18.0:
        return dict(best)
    return {}

def _build_subtitle_segment_map(subtitle_segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for segment in subtitle_segments or []:
        seg_id = str(segment.get("seg_id", "") or segment.get("id", "") or "").strip()
        if seg_id:
            mapping[seg_id] = dict(segment)
    return mapping

def _collect_scene_dialogue_signals(
    scene: Dict[str, Any],
    subtitle_segment_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    speakers: List[str] = []
    for subtitle_id in scene.get("subtitle_ids") or []:
        segment = subtitle_segment_map.get(str(subtitle_id or "").strip())
        if not segment:
            continue
        speaker = str(segment.get("speaker", "") or "").strip()
        if speaker:
            speakers.append(speaker)
    speaker_names = movie_story_edit_selection.sorted_unique_values(speakers)
    exchange_pairs = []
    compact_turns: List[str] = []
    for speaker in speakers:
        if not compact_turns or speaker != compact_turns[-1]:
            compact_turns.append(speaker)
    for left, right in zip(compact_turns, compact_turns[1:]):
        if left and right and left != right:
            exchange_pairs.append(f"{left}->{right}")
    return {
        "speaker_sequence": list(speakers),
        "speaker_names": speaker_names,
        "speaker_turns": len(speakers),
        "exchange_pairs": exchange_pairs,
    }

def _build_scene_candidate(
    scene: Dict[str, Any],
    index: int,
    total: int,
    parent_chunk: Dict[str, Any],
    boundary_candidates: List[float],
    subtitle_segment_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    scene_text = str(scene.get("subtitle_text", "") or " ".join(scene.get("subtitle_texts") or [])).strip()
    start = float(scene.get("start", 0.0) or 0.0)
    end = float(scene.get("end", start) or start)
    duration = max(end - start, 0.5)
    dialogue_signals = _collect_scene_dialogue_signals(scene, subtitle_segment_map)

    if parent_chunk:
        synthetic_chunk = dict(parent_chunk)
        synthetic_chunk["start"] = start
        synthetic_chunk["end"] = end
        synthetic_chunk["scene_id"] = str(scene.get("scene_id", "") or synthetic_chunk.get("scene_id", "") or "")
        synthetic_chunk["subtitle_ids"] = list(scene.get("subtitle_ids") or synthetic_chunk.get("subtitle_ids") or [])
        synthetic_chunk["aligned_subtitle_text"] = scene_text or str(synthetic_chunk.get("aligned_subtitle_text", "") or "")
        synthetic_chunk["real_narrative_state"] = str(
            synthetic_chunk.get("real_narrative_state", "") or synthetic_chunk.get("surface_dialogue_meaning", "") or scene_text
        )
        synthetic_chunk["highlight_score"] = max(float(synthetic_chunk.get("highlight_score", 0.0) or 0.0) * 0.9, 0.36)
        synthetic_chunk["raw_voice_retain_suggestion"] = bool(scene_text) or bool(
            synthetic_chunk.get("raw_voice_retain_suggestion")
        )
        if dialogue_signals["speaker_sequence"]:
            synthetic_chunk["speaker_sequence"] = list(dialogue_signals["speaker_sequence"])
        if dialogue_signals["speaker_names"]:
            synthetic_chunk["speaker_names"] = list(dialogue_signals["speaker_names"])
        if int(dialogue_signals.get("speaker_turns", 0) or 0) > 0:
            synthetic_chunk["speaker_turns"] = int(dialogue_signals.get("speaker_turns", 0) or 0)
        if dialogue_signals["exchange_pairs"]:
            synthetic_chunk["exchange_pairs"] = list(dialogue_signals["exchange_pairs"])
        candidate = build_candidate_from_plot_chunk(synthetic_chunk, index, total)
        candidate["selection_reason"] = list(dict.fromkeys(list(candidate.get("selection_reason") or []) + ["scene_refined"]))
    else:
        story_position = round((index - 1) / max(total - 1, 1), 3) if total > 1 else 0.5
        candidate = {
            "clip_id": f"scene_clip_{index:04d}",
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(duration, 3),
            "source": "scene",
            "story_index": index,
            "story_position": story_position,
            "story_stage_hint": "opening" if story_position <= 0.12 else "ending" if story_position >= 0.88 else "setup",
            "plot_function": "",
            "plot_role": "",
            "character_names": [],
            "subtitle_text": scene_text,
            "scene_summary": scene_text,
            "energy_score": 0.52 if scene_text else 0.4,
            "story_score": 0.42 if scene_text else 0.32,
            "emotion_score": 0.38 if scene_text else 0.3,
            "total_score": 0.45 if scene_text else 0.34,
            "raw_audio_worthy": bool(scene_text) or duration <= 4.5,
            "tags": ["scene_refined" if scene_text else "scene_fallback"],
            "source_scene_id": str(scene.get("scene_id", "") or ""),
            "source_segment_ids": list(scene.get("subtitle_ids") or []),
            "speaker_sequence": list(dialogue_signals["speaker_sequence"]),
            "speaker_names": list(dialogue_signals["speaker_names"]),
            "speaker_turns": int(dialogue_signals["speaker_turns"]),
            "exchange_pairs": list(dialogue_signals["exchange_pairs"]),
            "selection_reason": ["scene_refined" if scene_text else "scene_fallback"],
        }

    candidate["clip_id"] = f"scene_clip_{index:04d}"
    candidate["source"] = "scene"
    candidate["start"] = round(start, 3)
    candidate["end"] = round(end, 3)
    candidate["duration"] = round(duration, 3)
    candidate["subtitle_text"] = scene_text or str(candidate.get("subtitle_text", "") or "")
    candidate["scene_summary"] = str(candidate.get("scene_summary", "") or scene_text or "")
    candidate["raw_audio_worthy"] = bool(candidate.get("raw_audio_worthy")) or bool(scene_text) or duration <= 4.5
    candidate["energy_score"] = round(max(float(candidate.get("energy_score", 0.0) or 0.0), 0.58 if scene_text else 0.42), 3)
    candidate["source_scene_id"] = str(scene.get("scene_id", "") or candidate.get("source_scene_id", "") or "")
    candidate["source_segment_ids"] = list(scene.get("subtitle_ids") or candidate.get("source_segment_ids") or [])
    candidate["speaker_sequence"] = list(dialogue_signals.get("speaker_sequence") or candidate.get("speaker_sequence") or [])
    candidate["speaker_names"] = movie_story_edit_selection.sorted_unique_values(
        list(candidate.get("speaker_names") or []) + list(dialogue_signals.get("speaker_names") or [])
    )
    candidate["speaker_turns"] = int(dialogue_signals.get("speaker_turns", 0) or 0) or int(candidate.get("speaker_turns", 0) or 0)
    candidate["exchange_pairs"] = list(dialogue_signals.get("exchange_pairs") or candidate.get("exchange_pairs") or [])
    candidate["keyframe_candidates"] = list(scene.get("keyframe_candidates") or [])
    candidate["boundary_candidates"] = list(boundary_candidates or [])
    if scene_text and "scene_refined" not in list(candidate.get("tags") or []):
        candidate["tags"] = list(dict.fromkeys(list(candidate.get("tags") or []) + ["scene_refined"]))
    return enrich_candidate_evidence(candidate)

def _collect_scene_boundary_candidates(
    scene: Dict[str, Any],
    video_boundary_candidates: List[Dict[str, Any]],
) -> List[float]:
    start = float(scene.get("start", 0.0) or 0.0)
    end = float(scene.get("end", start) or start)
    boundaries = []
    for item in video_boundary_candidates or []:
        timestamp = float(item.get("time", start) or start)
        if start + 0.35 <= timestamp <= end - 0.35:
            boundaries.append(round(timestamp, 3))
    return sorted(dict.fromkeys(boundaries))

def _build_scene_candidates(
    *,
    scene_segments: List[Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    video_boundary_candidates: List[Dict[str, Any]],
    subtitle_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    total = len(scene_segments or [])
    subtitle_segment_map = _build_subtitle_segment_map(subtitle_segments)
    for idx, scene in enumerate(scene_segments or [], start=1):
        parent_chunk = _find_best_plot_chunk_for_scene(scene, plot_chunks)
        boundary_candidates = _collect_scene_boundary_candidates(scene, video_boundary_candidates)
        candidates.append(_build_scene_candidate(scene, idx, total, parent_chunk, boundary_candidates, subtitle_segment_map))
    return candidates

def _build_candidate_stats(
    *,
    subtitle_segments: List[Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    scene_segments: List[Dict[str, Any]],
    plot_candidate_clips: List[Dict[str, Any]],
    scene_candidate_clips: List[Dict[str, Any]],
    merged_candidate_clips: List[Dict[str, Any]],
    visual_mode: str,
    highlight_profile: Dict[str, Any],
    capabilities: Dict[str, Any],
    plot_audio_stats: Dict[str, Any],
    scene_audio_stats: Dict[str, Any],
) -> Dict[str, Any]:
    source_breakdown: Dict[str, int] = {}
    for clip in merged_candidate_clips or []:
        source = str(clip.get("source", "") or "unknown")
        source_breakdown[source] = source_breakdown.get(source, 0) + 1
    main_character_reference = movie_story_edit_selection.detect_main_character_reference(merged_candidate_clips)

    return {
        "visual_mode": visual_mode,
        "highlight_profile_id": str(highlight_profile.get("id", "general") or "general"),
        "highlight_profile_label": str(highlight_profile.get("label", "") or ""),
        "highlight_profile_source": str(highlight_profile.get("source", "") or ""),
        "highlight_profile_confidence": round(float(highlight_profile.get("confidence", 0.0) or 0.0), 3),
        "highlight_profile_reasons": list(highlight_profile.get("reasons") or [])[:6],
        "highlight_signal_route": str(highlight_profile.get("signal_route", "") or ""),
        "highlight_signal_modifiers": list(highlight_profile.get("signal_modifiers") or [])[:6],
        "highlight_signal_reasons": list(highlight_profile.get("signal_reasons") or [])[:6],
        "highlight_signal_metrics": dict(highlight_profile.get("signal_metrics") or {}),
        "main_character_reference": list(main_character_reference)[:3],
        "subtitle_segment_count": len(subtitle_segments or []),
        "plot_chunk_count": len(plot_chunks or []),
        "scene_segment_count": len(scene_segments or []),
        "plot_candidate_count": len(plot_candidate_clips or []),
        "scene_candidate_count": len(scene_candidate_clips or []),
        "merged_candidate_count": len(merged_candidate_clips or []),
        "raw_audio_candidate_count": sum(1 for clip in (merged_candidate_clips or []) if clip.get("raw_audio_worthy")),
        "audio_signal_candidate_count": sum(
            1 for clip in (merged_candidate_clips or []) if float(clip.get("audio_signal_score", 0.0) or 0.0) >= 0.5
        ),
        "source_breakdown": source_breakdown,
        "capabilities": dict(capabilities or {}),
        "plot_audio_stats": dict(plot_audio_stats or {}),
        "scene_audio_stats": dict(scene_audio_stats or {}),
    }

def _build_narrated_clip_pool(
    candidate_clips: List[Dict[str, Any]],
    scene_candidate_clips: List[Dict[str, Any]],
    narration_units: List[Dict[str, Any]],
    target_duration_seconds: int,
) -> List[Dict[str, Any]]:
    combined_candidates = movie_story_edit_selection.merge_unique_clips(candidate_clips, scene_candidate_clips)
    if not combined_candidates:
        return []

    desired_count = max(len(narration_units) * 2, round(target_duration_seconds / 18), 8)
    coverage_count = max(len(narration_units), round(target_duration_seconds / 30), 6)
    hero_clips = movie_story_edit_selection._select_diverse_clips(combined_candidates, desired_count)
    coverage_clips = _build_coverage_clips(combined_candidates, coverage_count)
    raw_audio_clips = movie_story_edit_selection._select_diverse_clips(
        (dict(item) for item in combined_candidates if item.get("raw_audio_worthy")),
        top_k=max(round(desired_count / 3), 2),
        lambda_relevance=0.78,
    )
    chronology_clips = sorted(
        (dict(item) for item in combined_candidates),
        key=lambda x: (float(x.get("start", 0.0) or 0.0), -float(x.get("total_score", 0.0) or 0.0)),
    )[:desired_count]
    return movie_story_edit_selection.merge_unique_clips(hero_clips, coverage_clips, raw_audio_clips, chronology_clips, scene_candidate_clips)

def _collect_matched_clips(narration_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clips: List[Dict[str, Any]] = []
    for match in narration_matches or []:
        clip_group = list(match.get("clip_group") or [])
        if clip_group:
            for item in clip_group:
                clip = dict(item)
                clip["prevent_merge"] = True
                clips.append(clip)
        elif match.get("clip"):
            clip = dict(match.get("clip") or {})
            clip["prevent_merge"] = True
            clips.append(clip)
    return clips


# Public names for new callers; underscored names above remain for old tests and
# to keep the extracted implementation easy to compare with the original file.
build_candidate_clips = _build_candidate_clips
build_scene_candidates = _build_scene_candidates
build_candidate_stats = _build_candidate_stats
build_narrated_clip_pool = _build_narrated_clip_pool
collect_matched_clips = _collect_matched_clips
build_scene_candidate = _build_scene_candidate
build_subtitle_segment_map = _build_subtitle_segment_map
collect_scene_dialogue_signals = _collect_scene_dialogue_signals
