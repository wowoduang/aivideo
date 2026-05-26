# -*- coding: utf-8 -*-
from __future__ import annotations

"""Budgeted frame sampling for two_round_visual."""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.two_round_visual",
    "role": "sample low-density global frames and detailed focus-segment frames",
    "called_by": ["app/services/movie_story/two_round_visual_narration.py"],
    "constraints": ["deterministic only", "raise on cv2 failure", "budget-controlled"],
}

from pathlib import Path
from typing import Any

from loguru import logger


def _require_cv2() -> Any:
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError("opencv-python is required for frame sampling") from exc
    return cv2


def _read_frame(*, capture: Any, fps: float, timestamp: float) -> Any:
    cv2 = _require_cv2()
    frame_index = max(int(timestamp * fps), 0)
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError(f"failed to read frame at {timestamp:.3f}s")
    return frame


def _resize_frame(*, frame: Any, max_long_side: int) -> Any:
    cv2 = _require_cv2()
    height, width = frame.shape[:2]
    long_side = max(height, width)
    if long_side <= max_long_side:
        return frame
    scale = max_long_side / float(long_side)
    new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
    return cv2.resize(frame, new_size)


def _save_frame(*, frame: Any, output_path: Path, jpeg_quality: int) -> None:
    cv2 = _require_cv2()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError(f"failed to save frame: {output_path}")


def _open_capture(*, video_path: Path) -> tuple[Any, float]:
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"failed to open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    return capture, fps


def sample_global_scene_frames(
    *,
    video_path: str | Path,
    scene_segments: list[dict[str, Any]],
    output_dir: str | Path,
    max_frames: int = 12,
    max_long_side: int = 768,
    jpeg_quality: int = 82,
) -> list[dict[str, Any]]:
    path = Path(video_path)
    capture, fps = _open_capture(video_path=path)
    output_root = Path(output_dir)
    selected = scene_segments[:max_frames]
    frames: list[dict[str, Any]] = []
    for index, scene in enumerate(selected, start=1):
        timestamp = (float(scene["start"]) + float(scene["end"])) / 2.0
        frame = _read_frame(capture=capture, fps=fps, timestamp=timestamp)
        frame = _resize_frame(frame=frame, max_long_side=max_long_side)
        output_path = output_root / "global" / f"global_{index:03d}.jpg"
        _save_frame(frame=frame, output_path=output_path, jpeg_quality=jpeg_quality)
        frames.append(
            {
                "frame_id": f"global_{index:03d}",
                "path": str(output_path),
                "timestamp": timestamp,
                "scene_id": str(scene["scene_id"]),
                "role": "global_scene_overview",
            }
        )
    capture.release()
    logger.info("two_round_visual sampled global scene frames: count={}", len(frames))
    return frames


def sample_focus_segment_frames(
    *,
    video_path: str | Path,
    focus_segments: list[dict[str, Any]],
    output_dir: str | Path,
    frames_per_segment: int = 2,
    max_long_side: int = 768,
    jpeg_quality: int = 82,
) -> list[dict[str, Any]]:
    path = Path(video_path)
    capture, fps = _open_capture(video_path=path)
    output_root = Path(output_dir)
    frames: list[dict[str, Any]] = []
    for segment in focus_segments:
        start = float(segment["start"])
        end = float(segment["end"])
        segment_id = str(segment["segment_id"])
        timestamps = _segment_timestamps(start=start, end=end, frames_per_segment=frames_per_segment)
        for index, timestamp in enumerate(timestamps, start=1):
            frame = _read_frame(capture=capture, fps=fps, timestamp=timestamp)
            frame = _resize_frame(frame=frame, max_long_side=max_long_side)
            output_path = output_root / "focus" / f"{segment_id}_{index:02d}.jpg"
            _save_frame(frame=frame, output_path=output_path, jpeg_quality=jpeg_quality)
            frames.append(
                {
                    "frame_id": f"{segment_id}_{index:02d}",
                    "path": str(output_path),
                    "timestamp": timestamp,
                    "segment_id": segment_id,
                    "role": "focus_segment_detail",
                }
            )
    capture.release()
    logger.info("two_round_visual sampled focus frames: count={}", len(frames))
    return frames


def _segment_timestamps(*, start: float, end: float, frames_per_segment: int) -> list[float]:
    if frames_per_segment <= 0:
        raise ValueError("frames_per_segment must be positive")
    if frames_per_segment == 1:
        return [(start + end) / 2.0]
    duration = max(end - start, 0.2)
    step = duration / float(frames_per_segment + 1)
    return [start + step * float(index) for index in range(1, frames_per_segment + 1)]
