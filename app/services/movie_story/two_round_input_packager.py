# -*- coding: utf-8 -*-
from __future__ import annotations

"""
two_round_input_packager.py

What this module is:
- Builds compact factual evidence packages for the two-round narration chain.

Why it exists:
- Backend value is to make the LLM input easy to judge, cost-controlled, and
  evidence-clear. This module combines selected highlights, subtitle evidence,
  visual evidence, and optional speech cues into one package per segment.

Input:
- selected_highlights
- highlight_narration_segments
- visual_evidence_by_highlight
- optional speech_cues_by_highlight

Output:
- two_round_input_packages

Producer:
- movie_story native/runtime evidence pipeline
- future manual segment selection converted to highlight-like records
- visual_highlight_evidence
- audio_speech_cues

Consumer:
- two_round_narration_chain

Formality:
- FORMAL INPUT PACKAGE BUILDER FOR TWO-ROUND NARRATION.

NOT FOR:
- selecting final highlights
- generating narration directly
- calling an LLM
- storing debug/trace markers as formal evidence

Failure policy:
- Missing one-to-one alignment between highlights and evidence raises. Do not
  silently drop incomplete segments.
"""

from typing import Any, Mapping, Sequence


__all__ = ["build_two_round_input_packages"]


def build_two_round_input_packages(
    selected_highlights: Sequence[Mapping[str, Any]],
    highlight_narration_segments: Sequence[Mapping[str, Any]],
    visual_evidence_by_highlight: Sequence[Mapping[str, Any]],
    *,
    speech_cues_by_highlight: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build compact per-highlight input packages for two-round narration.

    Input:
    - selected_highlights: target windows selected by auto or user flow.
    - highlight_narration_segments: subtitle/evidence package.
    - visual_evidence_by_highlight: visual anchor package.
    - speech_cues_by_highlight: optional speaker/audio cue package.

    Output:
    - two_round_input_packages.

    NOT FOR:
    - legacy/native narration generation.
    - debug/trace marker storage.
    - full-subtitle repeated prompting.
    """
    if not selected_highlights:
        raise ValueError("selected_highlights must not be empty")

    narration_index = _index_by_highlight_id(highlight_narration_segments, label="highlight_narration_segments")
    visual_index = _index_by_highlight_id(visual_evidence_by_highlight, label="visual_evidence_by_highlight")
    speech_index = _index_by_highlight_id(speech_cues_by_highlight or [], label="speech_cues_by_highlight")

    packages: list[dict[str, Any]] = []
    for item in selected_highlights:
        highlight_id = _required_str(item, "highlight_id")
        start = _required_float(item, "start")
        end = _required_float(item, "end")
        if highlight_id not in narration_index:
            raise RuntimeError(f"missing narration evidence for highlight_id={highlight_id}")
        if highlight_id not in visual_index:
            raise RuntimeError(f"missing visual evidence for highlight_id={highlight_id}")

        narration = narration_index[highlight_id]
        visual = visual_index[highlight_id]
        packages.append(
            {
                "highlight_id": highlight_id,
                "source": str(item.get("source") or "selected_highlight"),
                "time_range": [start, end],
                "duration": round(end - start, 3),
                "highlight_type": item.get("highlight_type"),
                "subtitle_evidence": {
                    "start": narration.get("start"),
                    "end": narration.get("end"),
                    "text": str(
                        narration.get("subtitle_text")
                        or narration.get("source_text")
                        or narration.get("text")
                        or ""
                    ).strip(),
                },
                "visual_evidence": visual,
                "speech_cues": speech_index.get(highlight_id, {}),
                "llm_input_policy": {
                    "intended_chain": "two_round_narration",
                    "do_not_repeat_full_subtitle": True,
                    "do_not_treat_visual_questions_as_facts": True,
                    "do_not_generate_narration_in_backend": True,
                    "highlight_is_selected_before_detailed_visual_sampling": True,
                },
            }
        )
    return packages


def _index_by_highlight_id(records: Sequence[Mapping[str, Any]], *, label: str) -> dict[str, Mapping[str, Any]]:
    """Index records by required unique highlight_id."""
    index: dict[str, Mapping[str, Any]] = {}
    for record in records:
        highlight_id = str(record.get("highlight_id") or "").strip()
        if not highlight_id:
            raise KeyError(f"{label} contains record without highlight_id")
        if highlight_id in index:
            raise RuntimeError(f"{label} contains duplicate highlight_id={highlight_id}")
        index[highlight_id] = record
    return index


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
