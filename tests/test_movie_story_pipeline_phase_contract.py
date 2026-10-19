from pathlib import Path

from app.services.movie_story.pipeline import run_first_three_stages
from app.services.movie_story.stage1_segmentation import build_segmentation_candidates
from app.services.movie_story.stage2_evidence import enrich_candidates_with_evidence
from app.services.movie_story.stage3_highlight_selection import select_highlights_with_report


def sample_subtitles():
    return [
        {"start": 0, "end": 3, "text": "前情提要 上集男主被误会"},
        {"start": 5, "end": 12, "text": "男主发现一份关键证据"},
        {"start": 14, "end": 22, "text": "女主开始怀疑老板背叛了他们"},
        {"start": 25, "end": 34, "text": "反派安排新的计划陷害男主"},
        {"start": 38, "end": 48, "text": "男主决定留下救人 关系发生变化"},
        {"start": 52, "end": 60, "text": "片尾 演职员表"},
    ]


def test_stage1_cuts_candidates_without_highlight_selection():
    scenes, stories, coverage = build_segmentation_candidates(
        "missing.mp4",
        sample_subtitles(),
        segmentation_mode="hybrid",
        prologue_end=0,
        story_end=60,
        video_boundary_candidates=[{"time": 24, "strength": "strong", "reason": ["video_boundary"]}],
    )

    assert scenes
    assert stories
    assert coverage["policy"] == "stage1_cut_all_no_highlight_filter"
    assert "target_minutes" in coverage["forbidden_inputs"]
    assert all("highlight_score" not in scene.__dict__ for scene in scenes)
    assert all(scene.video_end > scene.video_start for scene in scenes)
    assert coverage["coverage_ratio"] >= 0.95


def test_stage2_preserves_candidates_and_only_marks_drop_suggestions():
    scenes, stories, _ = build_segmentation_candidates("missing.mp4", sample_subtitles(), prologue_end=0, story_end=60)
    source = stories if stories else scenes
    evidence = enrich_candidates_with_evidence(
        source,
        sample_subtitles(),
        visual_cards={source[1].candidate_id: {"characters": ["男主"], "important_visual_detail": "掏出证据"}} if len(source) > 1 else {},
    )

    assert len(evidence) == len(source)
    assert any(item.drop_suggestion for item in evidence)
    assert all(item.video_end > item.video_start for item in evidence)
    assert all(item.split_merge_suggestion for item in evidence)
    assert all(item.evidence_start is not None and item.evidence_end is not None for item in evidence)


def test_stage3_is_only_selection_stage_and_audits_rejections():
    scenes, stories, _ = build_segmentation_candidates("missing.mp4", sample_subtitles(), prologue_end=0, story_end=60)
    evidence = enrich_candidates_with_evidence(stories if stories else scenes, sample_subtitles())

    strict = select_highlights_with_report(evidence, target_minutes=1, highlight_selectivity="strict")
    loose = select_highlights_with_report(evidence, target_minutes=1, highlight_selectivity="loose")

    assert strict["summary"]["policy"] == "stage3_is_the_only_stage_that_selects_highlights"
    assert len(loose["selected_highlights"]) >= len(strict["selected_highlights"])
    assert strict["rejected_candidates"] or loose["rejected_candidates"]
    for h in loose["selected_highlights"]:
        source = next(e for e in evidence if e.candidate_id == h.source_candidate_id)
        assert h.video_start == source.video_start
        assert h.video_end == source.video_end
        assert "highlight_score" in h.scores


def test_three_stage_pipeline_writes_complete_audit(tmp_path: Path):
    result = run_first_three_stages(
        video_path="missing.mp4",
        subtitle_segments=sample_subtitles(),
        output_dir=str(tmp_path),
        target_minutes=1,
        highlight_selectivity="balanced",
        export_audit_clips=False,
    )

    assert result["scene_candidates"]
    assert result["evidence_segments"]
    assert result["selected_highlights"]
    audit_dir = Path(result["audit_dir"])
    expected = [
        "01_scene_candidates",
        "02_draft_story_candidates",
        "03_evidence_segments",
        "04_split_merge_suggestions",
        "05_selected_highlights",
        "06_rejected_candidates",
    ]
    for stage in expected:
        stage_dir = audit_dir / stage
        assert (stage_dir / "manifest.json").exists()
        assert (stage_dir / "manifest.csv").exists()
        assert (stage_dir / "items_full.json").exists()
        assert (stage_dir / "summary.json").exists()
    assert (tmp_path / "movie_story_first_three_stages_v1.json").exists()
