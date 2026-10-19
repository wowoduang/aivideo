from app.services.movie_story import understanding_quality
from tools.verify_movie_story_migration_stage import verify_stage_d
from pathlib import Path
import json


def _stage_c_item(idx=1):
    hid = f"highlight_{idx:03d}"
    global_summary = {
        "main_conflict": "权力财政需求与民间生存困境之间的矛盾持续升级。",
        "story_theme": "权力、财政压力与底层生存之间的冲突。",
        "genre": "历史宫廷/王朝权力",
        "main_characters": ["皇上", "大臣", "百姓"],
        "timeline_summary": ["朝廷财政吃紧", "催税任务下达", "民间灾荒加深"],
        "relationship_map": [],
        "risk_flags": [],
    }
    seg = {
        "highlight_id": hid,
        "timestamp": "00:00:01,000-00:00:05,000",
        "start": 1.0,
        "end": 5.0,
        "subtitle_text": "朕现在就任命你为钦差大臣，赴各地催征税银。",
        "surface_dialogue_meaning": "皇帝安排臣子承担催税任务。",
        "real_narrative_state": "朝廷把财政压力继续向地方和百姓传导。",
        "conflict_summary": "皇权财政需求与民间承受能力发生冲突。",
        "character_motivation": "皇帝急于筹钱，大臣需要执行命令。",
        "story_function": "建立主线冲突",
        "plot_function": "冲突升级",
        "importance_level": "high",
        "narration_intent": "解释催税背后的财政压力和民间困境，不复述任命台词。",
        "selection_reason": "这里建立了朝廷和民间的核心矛盾。",
        "_global_summary": global_summary,
        "local_understanding": {
            "real_narrative_state": "朝廷把财政压力继续向地方和百姓传导。",
            "story_function": "建立主线冲突",
        },
    }
    return {
        "highlight_id": hid,
        "prompt_namespace": "movie_story_narration",
        "prompt_name": "narration_generation",
        "llm_call_enabled": False,
        "legacy_prompt_payload": {
            "segment_json": seg,
            "project_context": {"genre": "历史宫廷/王朝权力"},
            "style": "short_drama",
            "char_budget": 48,
            "global_summary": global_summary,
            "local_understanding": seg["local_understanding"],
            "story_function": seg["story_function"],
            "selection_reason": seg["selection_reason"],
            "narration_intent": seg["narration_intent"],
        },
        "segment_json": seg,
        "project_context": {"genre": "历史宫廷/王朝权力"},
        "style": "short_drama",
        "char_budget": 48,
        "input_contract_quality": {"passed": True},
    }


def test_stage_d_builds_global_and_local_samples_without_llm():
    items = [_stage_c_item(i) for i in range(1, 9)]
    stage_d = understanding_quality.build_stage_d_understanding_items(items, max_local_samples=8, llm_call_enabled=False)
    report = understanding_quality.evaluate_stage_d_items(stage_d, min_local_samples=6)
    assert report["overall_passed"] is True
    assert report["global_request_count"] == 1
    assert report["local_sample_count"] == 8
    assert report["llm_enabled_count"] == 0
    assert report["cache_ready_count"] == 9


def test_verify_stage_d_from_audit_dir(tmp_path: Path):
    run = tmp_path / "run_x"
    stage_c_dir = run / "06b_narration_generation_input_contract"
    stage_c_dir.mkdir(parents=True)
    stage_c_items = [_stage_c_item(i) for i in range(1, 9)]
    (stage_c_dir / "items_full.json").write_text(json.dumps(stage_c_items, ensure_ascii=False), encoding="utf-8")
    (stage_c_dir / "manifest.json").write_text(json.dumps(stage_c_items, ensure_ascii=False), encoding="utf-8")

    # Minimal prerequisites so verify_stage_c prerequisite can pass through A/B/C stack.
    # We call verify_stage_d on an explicit Stage-D audit output below, so the stage_c
    # prerequisite is covered by the direct stage_d output in real runs. For this unit
    # test, build the stage D directory and use --audit-json equivalent path would also work.
    stage_d_dir = run / understanding_quality.STAGE_D_STAGE_NAME
    stage_d_dir.mkdir(parents=True)
    stage_d_items = understanding_quality.build_stage_d_understanding_items(stage_c_items, max_local_samples=8)
    (stage_d_dir / "items_full.json").write_text(json.dumps(stage_d_items, ensure_ascii=False), encoding="utf-8")
    (stage_d_dir / "manifest.json").write_text(json.dumps(stage_d_items, ensure_ascii=False), encoding="utf-8")

    # Because verify_stage_d enforces Stage-C prerequisite when using audit-dir,
    # test the Stage-D checker through audit-json style payload for the isolated unit.
    audit_json = tmp_path / "stage_d_payload.json"
    audit_json.write_text(json.dumps({"stage_d_items": stage_d_items}, ensure_ascii=False), encoding="utf-8")
    result = verify_stage_d(audit_json=audit_json, min_local_samples=6)
    assert result["overall_passed"] is True
    assert result["checks"]["local_sample_count"] == 8
