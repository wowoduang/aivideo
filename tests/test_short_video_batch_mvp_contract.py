# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import pytest

from app.services.movie_story.short_video_batch.batch_pipeline import (
    build_short_video_batch_from_source_segments,
)
from app.services.movie_story.short_video_batch.batch_planner import build_short_video_plans
from app.services.movie_story.short_video_batch.source_segment_recall import (
    recall_short_video_candidates_from_source_segments,
)


def test_recall_short_video_candidates_from_source_segments() -> None:
    rows = [
        {
            "title": "朱重八不再相信王朝",
            "summary": "稻种被抢走后，朱重八看见秩序如何吃人。",
            "video_start": 100.0,
            "video_end": 180.0,
            "scores": {"highlight_score": 0.92},
            "selection_reasons": ["冲突明确", "情绪强"],
        }
    ]

    candidates = recall_short_video_candidates_from_source_segments(rows)

    assert len(candidates) == 1
    assert candidates[0].title == "朱重八不再相信王朝"
    assert candidates[0].duration_sec == 80.0
    assert candidates[0].score == 0.92


def test_build_short_video_plans_uses_one_theme_or_emo_line_only() -> None:
    rows = [
        {
            "title": "朱重八不再相信王朝",
            "summary": "稻种被抢走后，朱重八看见秩序如何吃人。",
            "video_start": 100.0,
            "video_end": 180.0,
            "highlight_score": 0.9,
        },
        {
            "title": "马姑娘救下朱重八",
            "summary": "在濠州城，被人认得本身就是一种秩序。",
            "video_start": 300.0,
            "video_end": 390.0,
            "highlight_score": 0.8,
        },
    ]
    candidates = recall_short_video_candidates_from_source_segments(rows)
    plans = build_short_video_plans(candidates, max_shorts=2)
    first = plans[0].to_dict()

    assert [plan.short_id for plan in plans] == ["short_001", "short_002"]
    assert first["theme_or_emo_line"] == "稻种被抢走后，朱重八看见秩序如何吃人。"
    assert first["line_type"] == "emo"
    assert "narration" not in first
    assert "script" not in first


def test_short_video_batch_pipeline_writes_theme_only_artifacts(tmp_path) -> None:
    rows = [
        {
            "title": "朱重八不再相信王朝",
            "summary": "稻种被抢走后，朱重八看见秩序如何吃人。",
            "timestamp": "00:01:40-00:03:00",
            "highlight_score": 0.95,
        }
    ]

    result = build_short_video_batch_from_source_segments(
        rows,
        output_dir=tmp_path,
        max_shorts=1,
    )

    plan_path = tmp_path / "short_video_plans.json"
    candidate_path = tmp_path / "short_video_candidates.json"

    assert plan_path.exists()
    assert candidate_path.exists()
    assert result["plans"][0]["short_id"] == "short_001"

    plans = json.loads(plan_path.read_text(encoding="utf-8"))
    first = plans["items"][0]

    assert plans["format"] == "aivideo_short_video_plans_v1"
    assert first["title"] == "朱重八不再相信王朝"
    assert first["theme_or_emo_line"] == "稻种被抢走后，朱重八看见秩序如何吃人。"
    assert "narration" not in first


def test_short_video_batch_pipeline_raises_on_empty_input(tmp_path) -> None:
    with pytest.raises(ValueError, match="source_segments"):
        build_short_video_batch_from_source_segments([], output_dir=tmp_path)


def test_no_highlight_like_public_naming_in_short_video_batch() -> None:
    root = __import__("pathlib").Path("app/services/movie_story/short_video_batch")
    public_tokens = [
        "highlight-like",
        "build_short_video_batch_from_highlight_segments",
        "recall_short_video_candidates_from_highlights",
    ]

    violations: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in public_tokens:
            if token in text:
                violations.append(f"{path}:{token}")

    assert violations == []
