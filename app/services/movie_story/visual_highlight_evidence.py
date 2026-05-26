# -*- coding: utf-8 -*-
from __future__ import annotations

"""
visual_highlight_evidence.py

What this module is:
- Builds factual visual evidence packages for candidate or selected highlights.

Why it exists:
- Backend should first prepare clear facts for candidate segments, then the
  selection process can decide which segments matter. After selection, the
  selected highlights can receive richer keyframe evidence.
- This module does not score or choose highlights. It only packages facts.

Input:
- highlight-like records
- keyframe records from visual_frame_sampler
- optional shot_candidates / scene_candidates
- optional highlight_narration_segments

Output:
- visual_evidence_by_highlight records.

Producer:
- movie_story runtime/native evidence pipeline
- future manual segment workflow converted to highlight-like records

Consumer:
- highlight selection
- two_round_input_packager
- optional VLM visual relation checker

Formality:
- FORMAL FACT-EVIDENCE PACKAGE BUILDER.

NOT FOR:
- deciding which segments are true highlights
- generating narration
- binding character names
- inferring character psychology
- pretending subtitle keyword scores are visual facts

Failure policy:
- Missing highlight ids, missing keyframes, or inconsistent alignment raises.
  Do not silently return partial visual evidence.
"""

from typing import Any, Mapping, Sequence


__all__ = ["build_visual_evidence_by_highlight"]


def build_visual_evidence_by_highlight(
    highlights: Sequence[Mapping[str, Any]],
    keyframes: Sequence[Mapping[str, Any]],
    *,
    shot_candidates: Sequence[Mapping[str, Any]] | None = None,
    scene_candidates: Sequence[Mapping[str, Any]] | None = None,
    highlight_narration_segments: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build factual visual evidence packages aligned to highlights.

    Input:
    - highlights: records with highlight_id/start/end.
    - keyframes: sampled frame records whose highlight_id equals highlight_id.
    - shot_candidates / scene_candidates: optional runtime boundaries.
    - highlight_narration_segments: optional subtitle/evidence package.

    Output:
    - visual evidence records aligned by highlight_id.

    NOT FOR:
    - final highlight selection.
    - narration generation.
    - character-name or address-term extraction.
    - claiming visual facts that were not observed by video/image analysis.
    """
    if not highlights:
        raise ValueError("highlights must not be empty")
    if not keyframes:
        raise ValueError("keyframes must not be empty")

    frames_by_highlight = _group_by_key(keyframes, "highlight_id")
    narration_by_highlight = _index_by_highlight_id(highlight_narration_segments or [])

    results: list[dict[str, Any]] = []
    for item in highlights:
        highlight_id = _required_str(item, "highlight_id")
        start = _required_float(item, "start")
        end = _required_float(item, "end")
        if end <= start:
            raise ValueError(f"invalid highlight window for {highlight_id}: {start}~{end}")

        item_frames = list(frames_by_highlight.get(highlight_id) or [])
        if not item_frames:
            raise RuntimeError(f"missing sampled keyframes for highlight_id={highlight_id}")

        narration_record = narration_by_highlight.get(highlight_id)
        sampling_stages = sorted({str(frame.get("sampling_stage") or "unknown") for frame in item_frames})
        results.append(
            {
                "highlight_id": highlight_id,
                "source": str(item.get("source") or "highlight_like_segment"),
                "time_range": [start, end],
                "duration": round(end - start, 3),
                "highlight_type": item.get("highlight_type"),
                "sampling_stages": sampling_stages,
                "keyframes": [_normalize_keyframe(frame) for frame in item_frames],
                "overlapping_shot_ids": _overlapping_ids(
                    shot_candidates or [],
                    start=start,
                    end=end,
                    id_keys=("shot_id", "candidate_id", "id"),
                ),
                "overlapping_scene_ids": _overlapping_ids(
                    scene_candidates or [],
                    start=start,
                    end=end,
                    id_keys=("scene_id", "candidate_id", "id"),
                ),
                "subtitle_context": _subtitle_context(narration_record),
                "backend_visual_facts": [],
                "uncertain_points": [
                    "No character names are inferred by this package.",
                    "No visual interpretation has been performed unless a VLM checker fills it later.",
                ],
                "questions_for_vlm": [
                    "Which side appears visually dominant or weaker in these frames?",
                    "Do the frames show confrontation, search, grabbing, chasing, fighting, or ordinary dialogue?",
                    "Are the same visible people/groups continuous across the sampled frames?",
                    "Is any important object or action visible that changes the meaning of this segment?",
                ],
            }
        )

    return results


def _normalize_keyframe(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one sampled keyframe record for downstream packages."""
    return {
        "time": _required_float(frame, "timestamp"),
        "frame_path": _required_str(frame, "frame_path"),
        "reason": str(frame.get("reason") or "sampled_keyframe"),
        "source": str(frame.get("source") or "highlight_like_segment"),
        "sampling_stage": str(frame.get("sampling_stage") or "unknown"),
    }


def _subtitle_context(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract compact subtitle context without inventing visual facts."""
    if not record:
        return {}
    text = str(
        record.get("subtitle_text")
        or record.get("source_text")
        or record.get("text")
        or ""
    ).strip()
    return {"start": record.get("start"), "end": record.get("end"), "text_excerpt": text[:500]}


def _group_by_key(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    """Group records by a required string key."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        value = _required_str(record, key)
        grouped.setdefault(value, []).append(record)
    return grouped


def _index_by_highlight_id(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Index records with optional highlight_id."""
    index: dict[str, Mapping[str, Any]] = {}
    for record in records:
        highlight_id = str(record.get("highlight_id") or "").strip()
        if highlight_id:
            index[highlight_id] = record
    return index


def _overlapping_ids(
    records: Sequence[Mapping[str, Any]],
    *,
    start: float,
    end: float,
    id_keys: Sequence[str],
) -> list[str]:
    """Return ids for records whose start/end overlaps the given segment."""
    ids: list[str] = []
    for record in records:
        try:
            record_start = float(record.get("start"))
            record_end = float(record.get("end"))
        except Exception:
            continue
        if record_end <= start or record_start >= end:
            continue
        for key in id_keys:
            value = str(record.get(key) or "").strip()
            if value:
                ids.append(value)
                break
    return sorted(set(ids))


def _required_str(record: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string field."""
    value = str(record.get(key) or "").strip()
    if not value:
        raise KeyError(f"record is missing required non-empty string key: {key}")
    return value


def _required_float(record: Mapping[str, Any], key: str) -> float:
    """Read a required numeric field."""
    if key not in record:
        raise KeyError(f"record is missing required numeric key: {key}")
    value = record[key]
    if value in (None, ""):
        raise ValueError(f"record key {key!r} is empty")
    return float(value)
