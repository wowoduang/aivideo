# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Build short_video_candidates.json and short_video_plans.json from one explicit
movie_story artifact file.

This is a manual verification tool for the short_video_batch MVP. It does not
generate full narration, TTS, subtitles, or rendered videos.
"""

__CONTEXT__ = {
    "layer": "tool",
    "domain": "movie_story.short_video_batch",
    "entry_points": [
        "main",
    ],
    "called_by": [
        "developer manual command",
    ],
    "decisions": [
        "2026-05: Provide an explicit-artifact manual tool before adding API/frontend integration.",
    ],
    "pending": [
        "Replace this manual step with API route after real artifacts validate the contracts.",
    ],
    "ai_constraints": [
        "Do not scan implicit task directories.",
        "Do not generate narration scripts.",
        "Do not render videos.",
    ],
}

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.movie_story.short_video_batch.source_segment_adapter import (
    build_short_video_batch_from_movie_story_artifact,
    load_source_segments_from_movie_story_artifact,
)


def _write_preview(path: Path, payload: dict[str, Any]) -> None:
    """Write optional preview JSON for dry-run inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, help="Explicit movie_story artifact JSON file")
    parser.add_argument("--output-dir", required=True, help="Directory for short_video_*.json artifacts")
    parser.add_argument("--source-type", default="movie_story_highlight")
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--max-shorts", type=int, default=6)
    parser.add_argument("--target-duration-sec", type=float, default=90.0)
    parser.add_argument("--preview-out", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.dry_run == args.apply:
        raise SystemExit("必须且只能指定 --dry-run 或 --apply")

    artifact_path = Path(args.artifact).resolve()
    output_dir = Path(args.output_dir).resolve()
    source_segments = load_source_segments_from_movie_story_artifact(
        artifact_path,
        source_type=args.source_type,
    )

    print(f"- artifact: {artifact_path}")
    print(f"- output_dir: {output_dir}")
    print(f"- source_segments: {len(source_segments)}")
    print(f"- max_candidates: {args.max_candidates}")
    print(f"- max_shorts: {args.max_shorts}")

    if args.dry_run:
        preview = {
            "artifact": str(artifact_path),
            "output_dir": str(output_dir),
            "source_segments": source_segments[: args.max_candidates],
        }
        if args.preview_out:
            preview_path = Path(args.preview_out).resolve()
            _write_preview(preview_path, preview)
            print(f"- preview_out: {preview_path}")
        print("[DRY-RUN] no short_video artifacts written")
        return 0

    result = build_short_video_batch_from_movie_story_artifact(
        artifact_path,
        output_dir=output_dir,
        source_type=args.source_type,
        max_candidates=args.max_candidates,
        max_shorts=args.max_shorts,
        target_duration_sec=args.target_duration_sec,
    )

    print(f"- candidates: {len(result['candidates'])}")
    print(f"- plans: {len(result['plans'])}")
    for name, path in result["artifacts"].items():
        print(f"- {name}: {path}")

    print("[APPLIED] built short video batch theme-only artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
