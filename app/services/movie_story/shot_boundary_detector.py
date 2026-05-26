# -*- coding: utf-8 -*-
from __future__ import annotations

"""Shot boundary detection for two_round_visual."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "deterministic shot boundary detection before first-round multimodal prompt",
    "called_by": [
        "app/services/movie_story/two_round_visual_narration.py",
        "app/services/movie_story/scene_segmenter.py",
    ],
    "constraints": [
        "deterministic only",
        "no fallback",
        "raise on missing video or cv2",
    ],
}

from pathlib import Path
from typing import Any

from loguru import logger


def _require_cv2() -> Any:
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError("opencv-python is required for shot detection") from exc
    return cv2


def _open_capture(*, video_path: Path) -> tuple[Any, float, int]:
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"failed to open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frame_count <= 0:
        raise RuntimeError(f"video has no frames: {video_path}")
    return capture, fps, frame_count


def _frame_mean_diff(*, current_frame: Any, previous_frame: Any) -> float:
    cv2 = _require_cv2()
    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(current_gray, previous_gray)
    return float(diff.mean())


def detect_shot_boundaries(
    *,
    video_path: str | Path,
    threshold: float = 28.0,
    min_shot_length_sec: float = 1.2,
    sample_stride: int = 3,
) -> list[dict[str, Any]]:
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"video not found: {path}")
    if sample_stride <= 0:
        raise ValueError("sample_stride must be positive")
    capture, fps, frame_count = _open_capture(video_path=path)
    min_frames = max(int(min_shot_length_sec * fps), 1)
    boundaries: list[dict[str, Any]] = []
    previous_frame = None
    shot_start = 0
    frame_index = 0
    shot_index = 1
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % sample_stride != 0:
            frame_index += 1
            continue
        if previous_frame is None:
            previous_frame = frame
            frame_index += 1
            continue
        score = _frame_mean_diff(current_frame=frame, previous_frame=previous_frame)
        if score >= threshold and frame_index - shot_start >= min_frames:
            end_frame = max(frame_index - 1, shot_start)
            boundaries.append(
                {
                    "shot_id": f"shot_{shot_index:04d}",
                    "start": shot_start / fps,
                    "end": end_frame / fps,
                    "start_frame": shot_start,
                    "end_frame": end_frame,
                    "cut_score": score,
                }
            )
            shot_index += 1
            shot_start = frame_index
        previous_frame = frame
        frame_index += 1
    capture.release()
    last_end_frame = max(frame_count - 1, shot_start)
    boundaries.append(
        {
            "shot_id": f"shot_{shot_index:04d}",
            "start": shot_start / fps,
            "end": last_end_frame / fps,
            "start_frame": shot_start,
            "end_frame": last_end_frame,
            "cut_score": 0.0,
        }
    )
    logger.info(
        "two_round_visual shot detection completed: shots={}, duration_sec={}",
        len(boundaries),
        round(frame_count / fps, 3),
    )
    return boundaries
