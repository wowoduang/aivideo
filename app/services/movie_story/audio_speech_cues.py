# -*- coding: utf-8 -*-
from __future__ import annotations

"""
audio_speech_cues.py

What this module is:
- Aligns real speech/speaker cue records to highlight-like movie_story segments.

Why it exists:
- Audio and speaker cues can help the two-round narration chain understand
  speaker turns and timing, but subtitle keyword emotion scores must not be
  mislabeled as audio emotion.

Input:
- highlight-like records
- speaker_units from ASR/diarization

Output:
- speech cue packages aligned by highlight_id.

Producer:
- Fun-ASR/Paraformer speaker context pipeline

Consumer:
- two_round_input_packager
- two_round_narration_chain

Formality:
- FORMAL INPUT BUILDER FOR TWO-ROUND NARRATION.

NOT FOR:
- character name binding
- address-term extraction
- subtitle keyword emotion scoring
- inferring character psychology
- replacing the two-round narration chain

Failure policy:
- Missing highlight ids or malformed timing raises. Do not silently fabricate
  audio cues from subtitle text.
"""

from typing import Any, Mapping, Sequence


__all__ = ["build_speech_turn_cues_for_highlights"]


def build_speech_turn_cues_for_highlights(
    highlights: Sequence[Mapping[str, Any]],
    speaker_units: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Align diarized speaker units to highlight-like segments."""
    if not highlights:
        raise ValueError("highlights must not be empty")

    results: list[dict[str, Any]] = []
    for item in highlights:
        highlight_id = _required_str(item, "highlight_id")
        start = _required_float(item, "start")
        end = _required_float(item, "end")
        if end <= start:
            raise ValueError(f"invalid highlight window for {highlight_id}: {start}~{end}")

        related = [
            unit for unit in speaker_units
            if _overlap_seconds(start, end, _required_float(unit, "start"), _required_float(unit, "end")) > 0
        ]
        speaker_sequence = [
            _speaker_id(unit)
            for unit in sorted(related, key=lambda item: float(item.get("start") or 0.0))
        ]
        compact_turns: list[str] = []
        for speaker_id in speaker_sequence:
            if not compact_turns or compact_turns[-1] != speaker_id:
                compact_turns.append(speaker_id)

        results.append(
            {
                "highlight_id": highlight_id,
                "time_range": [start, end],
                "speaker_ids": sorted(set(speaker_sequence)),
                "speaker_turn_count": len(compact_turns),
                "speaker_turn_sequence": compact_turns,
                "speech_unit_count": len(related),
                "not_inferred": [
                    "speaker ids are not character names",
                    "no subtitle address-term or pronoun resolution is performed",
                    "no acoustic emotion is inferred here",
                ],
            }
        )
    return results


def _speaker_id(unit: Mapping[str, Any]) -> str:
    """Read a required speaker id without mapping it to a character name."""
    value = str(unit.get("speaker") or unit.get("speaker_id") or unit.get("role_name") or "").strip()
    if not value:
        raise KeyError("speaker unit is missing speaker/speaker_id")
    return value


def _overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Return overlap duration in seconds."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


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
