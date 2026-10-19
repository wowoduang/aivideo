from app.services.movie_story.evidence_enrichment import (
    build_global_story_context,
    enrich_evidence_items,
    evaluate_evidence_items,
)


def test_stage_a_enriches_global_local_evidence():
    plot_chunks = [
        {
            "segment_id": "seg_1",
            "start": 180.0,
            "end": 195.0,
            "subtitle_text": "朕现在就任命你为钦差大臣，赴各地催征税银。皇上，可如今遍地饥民，岂是抗税。",
        },
        {
            "segment_id": "seg_2",
            "start": 156.0,
            "end": 180.0,
            "subtitle_text": "现在银库里的储银仅够一个月了。诺，皇上，再过两个月可臣妾的生日了。",
        },
    ]
    global_context = build_global_story_context(plot_chunks, {}, {}, video_title="测试视频")
    assert global_context["migration_quality"]["passed"] is True
    assert global_context["main_conflict"]
    assert len(global_context["timeline_summary"]) >= 3

    evidence = enrich_evidence_items(plot_chunks, global_context)
    assert len(evidence) == 2
    for item in evidence:
        assert item["_global_summary"]["main_conflict"]
        assert item["real_narrative_state"]
        assert item["conflict_summary"]
        assert item["character_motivation"]
        assert item["story_function"]
        assert item["narration_intent"]["intent"]
        assert item["evidence_completeness"]["passed"] is True

    report = evaluate_evidence_items(evidence)
    assert report["overall_passed"] is True
    assert report["pass_rate"] == 1.0
