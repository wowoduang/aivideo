# -*- coding: utf-8 -*-
from __future__ import annotations

"""
artifact_writer.py

Write short_video_* MVP artifacts into the current workspace task directory.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.artifact_writer",
    "entry_points": [
        "write_short_video_batch_artifacts",
    ],
    "called_by": [
        "batch_pipeline.py",
    ],
    "decisions": [
        "2026-05: Short-video batch writes dedicated short_video_* artifacts instead of overloading highlight files.",
        "2026-05: MVP short_video_plans.json contains title + one theme/emotion line, not full narration.",
    ],
    "pending": [
        "Add short_video_scripts.json and short_video_exports.json after script/render stages are implemented.",
    ],
    "ai_constraints": [
        "Do not write runtime artifacts into the project source tree.",
        "Do not include prompt/response/debug/frame files in user-facing exports.",
    ],
}

import json
from collections.abc import Sequence
from pathlib import Path

from app.services.movie_story.short_video_batch.contracts import (
    ShortVideoCandidate,
    ShortVideoPlan,
)


def _write_json(path: Path, data: object) -> None:
    """Write JSON using UTF-8 and LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def write_short_video_batch_artifacts(
    output_dir: str | Path,
    *,
    candidates: Sequence[ShortVideoCandidate],
    plans: Sequence[ShortVideoPlan],
) -> dict[str, str]:
    """Write MVP short-video batch artifacts and return artifact paths."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    candidate_path = root / "short_video_candidates.json"
    plan_path = root / "short_video_plans.json"

    _write_json(
        candidate_path,
        {
            "format": "aivideo_short_video_candidates_v1",
            "items": [candidate.to_dict() for candidate in candidates],
        },
    )
    _write_json(
        plan_path,
        {
            "format": "aivideo_short_video_plans_v1",
            "items": [plan.to_dict() for plan in plans],
        },
    )

    return {
        "short_video_candidates": str(candidate_path),
        "short_video_plans": str(plan_path),
    }
