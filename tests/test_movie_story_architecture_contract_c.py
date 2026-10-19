from __future__ import annotations

import json
from pathlib import Path

from app.services.movie_story.evidence_enrichment import build_global_story_context, enrich_evidence_items
from app.services.movie_story.highlight_planning import enrich_selected_highlights_for_planning
from app.services.movie_story.narration_contract import (
    build_stage_c_replay_items,
    evaluate_stage_c_replay_items,
)
from tools.verify_movie_story_migration_stage import verify_stage_c


def _write_stage(run: Path, stage: str, items):
    d = run / stage
    d.mkdir(parents=True, exist_ok=True)
    (d / "items_full.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def _sample_planned():
    base = [
        {"highlight_id": "highlight_001", "start": 1, "end": 8, "subtitle_text": "皇上，银库已经空了。", "plot_function": "信息揭露", "importance_level": "high"},
        {"highlight_id": "highlight_002", "start": 9, "end": 16, "subtitle_text": "朕现在任命你为钦差，赴各地催征税银。", "plot_function": "关键决定", "importance_level": "high"},
        {"highlight_id": "highlight_003", "start": 20, "end": 28, "subtitle_text": "可如今遍地饥民，岂是抗税。", "plot_function": "冲突升级", "importance_level": "high"},
    ]
    global_ctx = build_global_story_context(base)
    evidence = enrich_evidence_items(base, global_ctx)
    planned = enrich_selected_highlights_for_planning(evidence, global_ctx)
    return global_ctx, planned


def test_stage_c_builds_legacy_prompt_input_without_llm_call():
    global_ctx, planned = _sample_planned()
    replay = build_stage_c_replay_items(planned, global_ctx)
    report = evaluate_stage_c_replay_items(replay)

    assert report["overall_passed"] is True
    assert report["llm_enabled_count"] == 0
    assert report["over_budget_count"] == 0
    assert all(x["llm_call_enabled"] is False for x in replay)
    assert all(x["legacy_prompt_payload"]["segment_json"].get("real_narrative_state") for x in replay)
    assert all(x["legacy_prompt_payload"].get("project_context") for x in replay)
    assert all(x["legacy_prompt_payload"].get("char_budget") for x in replay)


def test_verify_stage_c_reads_runtime_audit_contract(tmp_path: Path):
    run = tmp_path / "run_001"
    global_ctx, planned = _sample_planned()
    replay = build_stage_c_replay_items(planned, global_ctx)

    _write_stage(run, "04_global_story_context", [{"global_context": global_ctx, **global_ctx}])
    _write_stage(run, "05b_highlight_planning_contract", planned)
    _write_stage(run, "06_scene_evidence_for_narration", planned)
    _write_stage(run, "06b_narration_generation_input_contract", replay)

    result = verify_stage_c(audit_dir=run)

    assert result["overall_passed"] is True
    assert result["checks"]["llm_enabled_count"] == 0
    assert result["checks"]["narration_input_stage_present"] is True
    assert "阶段 C 已达标" in result["next_targets"][-1]
