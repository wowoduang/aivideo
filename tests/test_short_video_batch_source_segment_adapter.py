# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import pytest

from app.services.movie_story.short_video_batch.source_segment_adapter import (
    build_short_video_batch_from_movie_story_artifact,
    load_source_segments_from_movie_story_artifact,
)


def test_load_source_segments_from_movie_story_artifact_items_schema(tmp_path) -> None:
    artifact = tmp_path / "movie_story_script_highlight_narration_segments.json"
    artifact.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "分论点一",
                        "narration": "稻种被抢走后，朱重八看见秩序如何吃人。",
                        "video_start": 100.0,
                        "video_end": 180.0,
                        "highlight_score": 0.93,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = load_source_segments_from_movie_story_artifact(artifact)

    assert len(rows) == 1
    assert rows[0]["title"] == "稻种被抢走后，朱重八看见秩序如何吃人。"
    assert rows[0]["summary"] == "稻种被抢走后，朱重八看见秩序如何吃人。"
    assert rows[0]["video_start"] == 100.0
    assert rows[0]["video_end"] == 180.0


def test_build_short_video_batch_from_movie_story_artifact_writes_theme_only_outputs(tmp_path) -> None:
    artifact = tmp_path / "movie_story_script_highlights.json"
    artifact.write_text(
        json.dumps(
            [
                {
                    "title": "朱重八不再相信王朝",
                    "summary": "稻种被抢走后，朱重八看见秩序如何吃人。",
                    "timestamp": "00:01:40-00:03:00",
                    "scores": {"highlight_score": 0.95},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_short_video_batch_from_movie_story_artifact(
        artifact,
        output_dir=tmp_path,
        max_shorts=1,
    )

    plan_path = tmp_path / "short_video_plans.json"
    plans = json.loads(plan_path.read_text(encoding="utf-8"))

    assert result["plans"][0]["short_id"] == "short_001"
    assert plans["items"][0]["theme_or_emo_line"] == "稻种被抢走后，朱重八看见秩序如何吃人。"
    assert "narration" not in plans["items"][0]
    assert "script" not in plans["items"][0]


def test_load_source_segments_from_movie_story_artifact_rejects_unsupported_schema(tmp_path) -> None:
    artifact = tmp_path / "bad.json"
    artifact.write_text(json.dumps({"unexpected": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="不支持"):
        load_source_segments_from_movie_story_artifact(artifact)
