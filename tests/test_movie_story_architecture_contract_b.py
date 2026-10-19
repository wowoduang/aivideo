from __future__ import annotations

import json
from pathlib import Path

from app.services.movie_story.evidence_enrichment import build_global_story_context, enrich_evidence_items
from app.services.movie_story.highlight_planning import (
    enrich_selected_highlights_for_planning,
    evaluate_stage_b_highlights,
)
from tools.verify_movie_story_migration_stage import verify_stage_b


def _write_stage(run: Path, stage: str, items):
    d = run / stage
    d.mkdir(parents=True, exist_ok=True)
    (d / "items_full.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def test_stage_b_planning_enriches_legacy_narration_input_contract():
    base = [
        {"highlight_id": "highlight_001", "start": 1, "end": 8, "subtitle_text": "皇上，银库已经空了。", "plot_function": "信息揭露", "importance_level": "high"},
        {"highlight_id": "highlight_002", "start": 9, "end": 16, "subtitle_text": "朕现在任命你为钦差，赴各地催征税银。", "plot_function": "关键决定", "importance_level": "high"},
        {"highlight_id": "highlight_003", "start": 20, "end": 28, "subtitle_text": "可如今遍地饥民，岂是抗税。", "plot_function": "冲突升级", "importance_level": "high"},
    ]
    global_ctx = build_global_story_context(base)
    evidence = enrich_evidence_items(base, global_ctx)
    planned = enrich_selected_highlights_for_planning(evidence, global_ctx)
    report = evaluate_stage_b_highlights(planned, min_type_count=2, min_arc_count=2)

    assert report["overall_passed"] is True
    assert all(x.get("selection_reason") for x in planned)
    assert all(x.get("story_role") for x in planned)
    assert all(x.get("narration_generation_input", {}).get("global_summary") for x in planned)
    assert all(x.get("narration_generation_input", {}).get("char_budget") for x in planned)


def test_verify_stage_b_reads_audit_contract(tmp_path: Path):
    run = tmp_path / "run_001"
    base = [
        {"highlight_id": "highlight_001", "start": 1, "end": 8, "subtitle_text": "皇上，银库已经空了。", "plot_function": "信息揭露", "importance_level": "high"},
        {"highlight_id": "highlight_002", "start": 9, "end": 16, "subtitle_text": "朕现在任命你为钦差，赴各地催征税银。", "plot_function": "关键决定", "importance_level": "high"},
        {"highlight_id": "highlight_003", "start": 20, "end": 28, "subtitle_text": "可如今遍地饥民，岂是抗税。", "plot_function": "冲突升级", "importance_level": "high"},
    ]
    global_ctx = build_global_story_context(base)
    evidence = enrich_evidence_items(base, global_ctx)
    planned = enrich_selected_highlights_for_planning(evidence, global_ctx)
    _write_stage(run, "04_global_story_context", [{"global_context": global_ctx, **global_ctx}])
    _write_stage(run, "05b_highlight_planning_contract", planned)
    _write_stage(run, "06_scene_evidence_for_narration", planned)

    result = verify_stage_b(audit_dir=run, min_pass_rate=0.9)

    assert result["overall_passed"] is True
    assert result["checks"]["highlight_planning_stage_present"] is True
    assert "阶段 B 已达标" in result["next_targets"][-1]
