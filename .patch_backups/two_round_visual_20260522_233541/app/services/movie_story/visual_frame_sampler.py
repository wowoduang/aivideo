# -*- coding: utf-8 -*-
from __future__ import annotations

"""
visual_frame_sampler.py

What this module is:
- Two-stage factual frame sampling for movie_story highlight workflow.

Why it exists:
- Backend should prepare clear factual evidence first, then let highlight
  selection decide which segments deserve deeper visual inspection.
- Candidate segments get a small factual frame budget.
- Selected highlights get a larger evidence frame budget.
- No visual-priority score is required here.

Input:
- video_path
- candidate/highlight records with highlight_id/start/end
- output_dir

Output:
- keyframe records aligned by highlight_id and sampling_stage.

Producer:
- visual_highlight_evidence
- future candidate fact preparation and selected-highlight enrichment workflows

Consumer:
- two_round_input_packager
- optional VLM visual relation checker

Formality:
- FORMAL FACT-EVIDENCE BUILDER FOR TWO-ROUND NARRATION.

NOT FOR:
- deciding which candidates are true highlights
- changing user-selected boundaries
- generating narration
- inferring character names
- inferring character psychology
- replacing VLM visual interpretation

Failure policy:
- Missing video_path, invalid timestamps, unreadable video, or failed frame read
  is a data/configuration error. Raise instead of silently returning empty
  visual evidence.
"""

from pathlib import Path
from typing import Any, Mapping, Sequence


__all__ = [
    "candidate_fact_frame_budget",
    "selected_highlight_frame_budget",
    "sample_times_for_candidate_fact",
    "sample_times_for_selected_highlight",
    "sample_frame_at_time",
    "sample_keyframes_for_candidate_facts",
    "sample_keyframes_for_selected_highlights",
]


def candidate_fact_frame_budget(start: float, end: float, *, max_frames: int = 2) -> int:
    """Choose a small frame budget for pre-selection factual evidence.

    Input:
    - start/end: candidate segment bounds in seconds.
    - max_frames: hard cap for candidate-stage cost.

    Output:
    - 1 or 2 frames by default.

    NOT FOR:
    - ranking highlights.
    - deciding emotional value.
    - detailed visual understanding.
    """
    duration = _valid_duration(start, end)
    if max_frames <= 0:
        raise ValueError(f"max_frames must be positive, got {max_frames}")
    if duration <= 8:
        return 1
    return min(2, int(max_frames))


def selected_highlight_frame_budget(start: float, end: float, *, max_frames: int = 6) -> int:
    """Choose a richer frame budget after highlight selection.

    Input:
    - start/end: selected highlight bounds in seconds.
    - max_frames: hard cap for selected-highlight visual cost.

    Output:
    - Cost-controlled frame count, usually 2-6.

    NOT FOR:
    - selecting highlights.
    - changing highlight boundaries.
    - replacing VLM interpretation.
    """
    duration = _valid_duration(start, end)
    if max_frames <= 0:
        raise ValueError(f"max_frames must be positive, got {max_frames}")
    if duration <= 10:
        count = 2
    elif duration <= 30:
        count = 3
    elif duration <= 60:
        count = 5
    else:
        count = 6
    return min(count, int(max_frames))


def sample_times_for_candidate_fact(start: float, end: float, *, max_frames: int = 2) -> list[float]:
    """Return timestamps for cheap candidate-stage factual evidence."""
    return _sample_times(start, end, candidate_fact_frame_budget(start, end, max_frames=max_frames))


def sample_times_for_selected_highlight(start: float, end: float, *, max_frames: int = 6) -> list[float]:
    """Return timestamps for post-selection selected-highlight evidence."""
    return _sample_times(start, end, selected_highlight_frame_budget(start, end, max_frames=max_frames))


def sample_frame_at_time(
    video_path: str | Path,
    timestamp_seconds: float,
    output_path: str | Path,
    *,
    max_edge: int = 960,
) -> Path:
    """Extract one factual frame from a video at a timestamp.

    Failure policy:
    - Missing cv2, unreadable video, failed frame read, or failed frame write
      raises RuntimeError.
    """
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("OpenCV/cv2 is required for frame extraction") from exc

    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(src)

    timestamp = float(timestamp_seconds)
    if timestamp < 0:
        raise ValueError(f"timestamp_seconds must be non-negative, got {timestamp}")

    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"failed to open video for frame extraction: {src}")

    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = cap.read()
    finally:
        cap.release()

    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame at {timestamp:.3f}s from {src}")

    frame = _resize_keep_ratio(frame, max_edge=max_edge)
    written = cv2.imwrite(str(dst), frame)
    if not written:
        raise RuntimeError(f"failed to write keyframe: {dst}")
    return dst


def sample_keyframes_for_candidate_facts(
    video_path: str | Path,
    candidates: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    *,
    max_frames_per_candidate: int = 2,
) -> list[dict[str, Any]]:
    """Sample cheap factual keyframes before final highlight selection.

    Input:
    - candidates: records with highlight_id/start/end.
    - video_path/output_dir: frame extraction source and destination.

    Output:
    - keyframe records with sampling_stage="candidate_fact".

    NOT FOR:
    - final selected-highlight visual detail.
    - judging whether a candidate is good.
    """
    return _sample_keyframes(
        video_path,
        candidates,
        output_dir,
        sampling_stage="candidate_fact",
        max_frames=max_frames_per_candidate,
    )


def sample_keyframes_for_selected_highlights(
    video_path: str | Path,
    selected_highlights: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    *,
    max_frames_per_highlight: int = 6,
) -> list[dict[str, Any]]:
    """Sample richer factual keyframes after highlight selection.

    Input:
    - selected_highlights: records with highlight_id/start/end.

    Output:
    - keyframe records with sampling_stage="selected_highlight_detail".

    NOT FOR:
    - modifying selected highlight boundaries.
    - generating narration.
    """
    return _sample_keyframes(
        video_path,
        selected_highlights,
        output_dir,
        sampling_stage="selected_highlight_detail",
        max_frames=max_frames_per_highlight,
    )


def _sample_keyframes(
    video_path: str | Path,
    items: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    *,
    sampling_stage: str,
    max_frames: int,
) -> list[dict[str, Any]]:
    """Shared extractor for explicit candidate/highlight time windows."""
    if not items:
        raise ValueError("items must not be empty")
    if sampling_stage not in {"candidate_fact", "selected_highlight_detail"}:
        raise ValueError(f"unsupported sampling_stage: {sampling_stage}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for item in items:
        highlight_id = _required_str(item, "highlight_id")
        start = _required_float(item, "start")
        end = _required_float(item, "end")
        if sampling_stage == "candidate_fact":
            times = sample_times_for_candidate_fact(start, end, max_frames=max_frames)
        else:
            times = sample_times_for_selected_highlight(start, end, max_frames=max_frames)

        for index, timestamp in enumerate(times):
            safe_id = _safe_file_part(highlight_id)
            time_ms = int(round(timestamp * 1000))
            frame_path = out / f"{safe_id}_{sampling_stage}_{index + 1:02d}_{time_ms:09d}.jpg"
            sample_frame_at_time(video_path, timestamp, frame_path)
            records.append(
                {
                    "highlight_id": highlight_id,
                    "source": str(item.get("source") or "highlight_like_segment"),
                    "sampling_stage": sampling_stage,
                    "start": start,
                    "end": end,
                    "timestamp": timestamp,
                    "frame_path": str(frame_path),
                    "reason": f"{sampling_stage}_{index + 1}_of_{len(times)}",
                }
            )

    return records


def _sample_times(start: float, end: float, count: int) -> list[float]:
    """Return deterministic timestamps for a valid time window."""
    if count <= 0:
        raise ValueError(f"count must be positive, got {count}")
    start_f = float(start)
    duration = _valid_duration(start, end)

    if count == 1:
        fractions = [0.5]
    elif count == 2:
        fractions = [0.33, 0.67]
    elif count == 3:
        fractions = [0.2, 0.5, 0.8]
    else:
        fractions = [(index + 1) / (count + 1) for index in range(count)]
    return [round(start_f + duration * fraction, 3) for fraction in fractions]


def _valid_duration(start: float, end: float) -> float:
    """Return duration after validating start/end."""
    start_f = float(start)
    end_f = float(end)
    if end_f <= start_f:
        raise ValueError(f"invalid time range: start={start_f}, end={end_f}")
    return end_f - start_f


def _resize_keep_ratio(frame: Any, *, max_edge: int) -> Any:
    """Resize an OpenCV frame while preserving aspect ratio."""
    if max_edge <= 0:
        raise ValueError(f"max_edge must be positive, got {max_edge}")
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= max_edge:
        return frame

    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("OpenCV/cv2 is required for frame resizing") from exc

    scale = max_edge / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


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


def _safe_file_part(value: str) -> str:
    """Create a filename-safe id segment without path traversal."""
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value))
    safe = safe.strip("._-")
    if not safe:
        raise ValueError(f"invalid file-safe id from value: {value!r}")
    return safe[:80]
