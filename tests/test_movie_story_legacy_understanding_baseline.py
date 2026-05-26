from __future__ import annotations

from app.services.movie_story.legacy_understanding_adapter import (
    build_understanding_script_payload,
    build_understanding_baseline_report,
    run_legacy_understanding_chain,
    select_story_highlights_with_legacy_priority,
)
from app.services.movie_story.quality_gate import _validate_pipeline_quality
from app.services.movie_story.highlight_runtime import _safe_plan_story_highlights
from app.services.movie_story.movie_story_native_engine import _BLOCKING_UNDERSTANDING_QUALITY_ISSUES
from app.services.movie_story.legacy_segment_understanding import enrich_legacy_segment_understanding
from app.services.movie_story.stage3_highlight_selection import select_highlights_with_report
from app.services.generate_narration_script_clean import _build_script_item


def test_legacy_understanding_chain_calls_old_deep_understanding_stages(monkeypatch):
    calls = []

    def fake_global(plot_chunks, api_key="", base_url="", model=""):
        calls.append("global")
        assert api_key == "key"
        return {"main_storyline": "old global story", "timeline_progression": ["a"]}

    def fake_context(**kwargs):
        calls.append("context")
        return dict(kwargs["existing_global_summary"])

    def fake_fuse(scenes, frame_records, visual_observations):
        calls.append("fuse")
        return [{"segment_id": "s1", "scene_id": "s1", "start": 0, "end": 10, "subtitle_text": "plot"}]

    def fake_local(scene_evidence, api_key="", base_url="", model=""):
        calls.append("local")
        assert model == "model"
        out = [dict(x) for x in scene_evidence]
        out[0]["local_understanding"] = {"core_event": "truth"}
        return out

    def fake_enrich(items, global_summary):
        return [dict(x, enriched=True) for x in items]

    def fake_validate(scene_evidence, global_summary, api_key="", base_url="", model=""):
        calls.append("validation")
        out = [dict(x) for x in scene_evidence]
        out[0]["story_validation"] = {"validator_status": "pass"}
        return out

    def fake_plan(scene_evidence, global_summary, full_subtitle_summary, api_key="", base_url="", model=""):
        calls.append("highlight_plan")
        assert scene_evidence[0]["legacy_segment_understanding"]["source"] == "legacy_highlight_selector_segment_model"
        return {"selected_segment_ids": ["s1"], "must_keep_ranges": []}

    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.build_global_summary", fake_global)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.build_global_story_context", fake_context)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.fuse_scene_evidence", fake_fuse)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.add_local_understanding", fake_local)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.enrich_evidence_items", fake_enrich)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.validate_story_segments", fake_validate)
    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter.plan_story_highlights", fake_plan)
    monkeypatch.setattr(
        "app.services.movie_story.legacy_understanding_adapter._select_final_story_evidence",
        lambda items: list(items),
    )

    result = run_legacy_understanding_chain(
        plot_chunks=[{"scene_id": "s1", "start": 0, "end": 10, "subtitle_text": "plot"}],
        frame_records=[],
        full_subtitle_understanding={"subtitle_understanding_status": "ok"},
        api_key="key",
        base_url="url",
        model="model",
        video_title="demo",
        target_minutes=8,
        narrative_strategy="chronological",
        accuracy_priority="high",
    )

    assert calls == ["global", "context", "fuse", "local", "validation", "highlight_plan"]
    assert result["global_story_understanding"]["main_storyline"] == "old global story"
    assert result["scene_evidence"][0]["local_understanding"]["core_event"] == "truth"
    assert result["scene_evidence"][0]["legacy_segment_understanding"]["shot_role"]
    assert result["story_validation"][0]["validator_status"] == "pass"
    assert result["llm_highlight_plan"]["selected_segment_ids"] == ["s1"]


def test_legacy_segment_understanding_ports_old_per_segment_semantics():
    result = enrich_legacy_segment_understanding(
        [
            {
                "segment_id": "s1",
                "start": 0,
                "end": 5,
                "subtitle_text": "张三：你为什么背叛我？李四：我也是被逼的。王五：够了。",
                "plot_function": "冲突升级",
                "importance_level": "high",
                "local_understanding": {"characters": ["张三"], "core_event": "关系破裂"},
            }
        ]
    )

    item = result[0]
    legacy = item["legacy_segment_understanding"]
    assert item["shot_role"] in {"dialogue_exchange", "ensemble_relation"}
    assert item["speaker_sequence"] == ["张三", "李四", "王五"]
    assert item["exchange_pairs"] == ["张三->李四", "李四->王五"]
    assert item["local_understanding"]["legacy_segment_understanding"]["primary_evidence"]
    assert set(item["local_understanding"]["characters"]) >= {"张三", "李四", "王五"}


def test_typed_highlight_selection_does_not_override_llm_plan(monkeypatch):
    captured = {}

    def fake_extract(scene_evidence, cut_points, highlight_selectivity="balanced"):
        captured["ids"] = [x["segment_id"] for x in scene_evidence]
        return [{"highlight_id": "h1", "segment_id": "llm", "start": 0, "end": 5}]

    monkeypatch.setattr("app.services.movie_story.legacy_understanding_adapter._extract_story_highlights", fake_extract)

    result, report = select_story_highlights_with_legacy_priority(
        scene_evidence=[
            {"segment_id": "llm", "start": 0, "end": 5, "llm_highlight_selected": True},
            {"segment_id": "typed_only", "start": 5, "end": 10, "highlight_score": 99},
        ],
        scene_cut_points=[],
        highlight_selectivity="balanced",
        full_subtitle_understanding={},
        llm_highlight_plan={"selected_segment_ids": ["llm"]},
    )

    assert captured["ids"] == ["llm"]
    assert result[0]["segment_id"] == "llm"
    assert report["selection_source"] == "legacy_llm_highlight_plan"


def test_quality_gate_fails_when_understanding_outputs_are_missing():
    issues = _validate_pipeline_quality(
        full_subtitle_understanding={"subtitle_understanding_status": "ok", "highlight_windows": [{"start": 0, "end": 5}]},
        llm_highlight_plan={"selected_segment_ids": ["s1"]},
        story_highlights=[{"highlight_id": "h1", "start": 0, "end": 5, "scene_align_mode": "semantic_keep"}],
        script_items=[{"segment_id": "s1", "llm_highlight_selected": True, "OST": 2}],
        highlight_only=False,
        scene_evidence=[{"segment_id": "s1", "start": 0, "end": 5}],
        understanding_baseline_report={"passed": False},
    )

    assert "legacy_understanding_baseline_failed" in issues
    assert "segment_local_understanding_missing" in issues
    assert "story_validation_missing" in issues


def test_baseline_failure_does_not_hide_generated_script_when_core_understanding_exists():
    assert "legacy_understanding_baseline_failed" not in _BLOCKING_UNDERSTANDING_QUALITY_ISSUES
    assert "scene_evidence_missing" in _BLOCKING_UNDERSTANDING_QUALITY_ISSUES
    assert "segment_local_understanding_missing" in _BLOCKING_UNDERSTANDING_QUALITY_ISSUES
    assert "story_validation_missing" in _BLOCKING_UNDERSTANDING_QUALITY_ISSUES


def test_native_strategy_baseline_report_is_not_fake_passed():
    report = build_understanding_baseline_report(
        has_llm=False,
        strategy="native_runtime",
        full_subtitle_understanding={},
        global_story_understanding={},
        scene_evidence=[],
        llm_highlight_plan={},
        story_highlights=[],
        narration_script=[],
    )

    assert report["status"] == "not_applicable"
    assert report["passed"] is None
    assert report["issues"] == []


def test_parse_failed_full_subtitle_can_pass_with_fallback_windows():
    report = build_understanding_baseline_report(
        has_llm=True,
        strategy="legacy_understanding",
        full_subtitle_understanding={
            "subtitle_understanding_status": "parse_failed",
            "highlight_windows": [{"start": 0, "end": 5}],
            "subtitle_timeline_digest": "fallback digest",
        },
        global_story_understanding={"main_storyline": "global story"},
        scene_evidence=[
            {
                "segment_id": "s1",
                "local_understanding": {"core_event": "truth"},
                "story_validation": {"validator_status": "pass"},
            }
        ],
        llm_highlight_plan={},
        story_highlights=[{"highlight_id": "h1", "segment_id": "s1"}],
        narration_script=[{"segment_id": "s1", "narration": "truth"}],
    )

    assert report["passed"] is True
    assert "full_subtitle_understanding" not in report["issues"]


def test_understanding_script_contains_whole_story_and_each_segment_understanding():
    payload = build_understanding_script_payload(
        strategy="legacy_understanding",
        full_subtitle_understanding={"subtitle_understanding_status": "ok", "main_storyline": "full story"},
        global_story_understanding={"main_storyline": "global story", "timeline_progression": ["a", "b"]},
        scene_evidence=[
            {
                "segment_id": "s1",
                "scene_id": "s1",
                "start": 0,
                "end": 5,
                "subtitle_text": "张三发现真相",
                "surface_dialogue_meaning": "发现真相",
                "real_narrative_state": "人物处境反转",
                "plot_function": "反转",
                "importance_level": "high",
                "local_understanding": {"core_event": "真相出现", "characters": ["张三"]},
                "legacy_segment_understanding": {"shot_role": "single_focus", "primary_evidence": "inner_state_support"},
                "story_validation": {"validator_status": "pass"},
            }
        ],
        story_highlights=[{"highlight_id": "h1", "segment_id": "s1"}],
        llm_highlight_plan={"selected_segment_ids": ["s1"]},
        narration_script=[{"_id": 1, "segment_id": "s1", "narration": "真相终于出现。"}],
        understanding_baseline_report={"passed": True},
    )

    assert payload["artifact"] == "movie_story_understanding_script"
    assert payload["global_story_understanding"]["main_storyline"] == "global story"
    assert payload["segment_understandings"][0]["local_understanding"]["core_event"] == "真相出现"
    assert payload["segment_understandings"][0]["legacy_segment_understanding"]["shot_role"] == "single_focus"
    assert payload["narration_script"][0]["narration"] == "真相终于出现。"
    assert payload["counts"]["segment_understandings"] == 1


def test_video_script_item_keeps_segment_understanding_fields():
    item = _build_script_item(
        1,
        {
            "segment_id": "s1",
            "scene_id": "s1",
            "start": 1,
            "end": 8,
            "timestamp": "00:00:01,000-00:00:08,000",
            "main_text_evidence": "张三发现真相，局势反转。",
            "plot_function": "反转",
            "importance_level": "high",
            "surface_dialogue_meaning": "发现真相",
            "real_narrative_state": "人物掌握关键信息，局势开始反转",
            "conflict_summary": "张三与对手的信息差改变",
            "character_motivation": "张三想确认真相",
            "story_function": "制造转折",
            "local_understanding": {
                "core_event": "真相出现",
                "characters": ["张三"],
                "legacy_segment_understanding": {"shot_role": "single_focus", "primary_evidence": "inner_state_support"},
            },
            "story_validation": {"validator_status": "pass", "raw_voice_keep": False},
            "legacy_segment_understanding": {"shot_role": "single_focus", "primary_evidence": "inner_state_support"},
        },
        {"narration": "张三终于发现真相，局势开始反转。", "risk_note": "grounded"},
        "picture",
        {"arc": "全剧主线"},
        "general",
    )

    assert item["global_arc"] == "全剧主线"
    assert item["risk_note"] == "grounded"
    assert item["real_narrative_state"] == "人物掌握关键信息，局势开始反转"
    assert item["local_understanding"]["core_event"] == "真相出现"
    assert item["story_validation"]["validator_status"] == "pass"
    assert item["legacy_segment_understanding"]["shot_role"] == "single_focus"


def test_coverage_repair_uses_only_eligible_candidates():
    weak_repair = [
        {
            "candidate_id": f"weak_{i}",
            "video_start": i * 10,
            "video_end": i * 10 + 8,
            "subtitle_text": "日常寒暄",
            "plot_function": "铺垫",
            "importance_level": "low",
            "drop_suggestion": True,
            "drop_reason": "weak",
        }
        for i in range(20)
    ]
    strong = [
        {
            "candidate_id": "strong_1",
            "video_start": 300,
            "video_end": 315,
            "subtitle_text": "真相曝光，冲突升级。",
            "plot_function": "信息揭露",
            "importance_level": "high",
            "information_tags": ["真相"],
            "emotion_tags": ["紧张"],
            "visual_evidence": {"key_action": "真相曝光"},
            "character_trace": {"goal_change_hint": True, "key_action": "继续调查"},
        }
    ]

    report = select_highlights_with_report(strong + weak_repair, target_minutes=5, highlight_selectivity="balanced")

    selected_ids = {x.source_candidate_id for x in report["selected_highlights"]}
    assert selected_ids == {"strong_1"}
    assert report["summary"]["fallback_report"]["fallback_added_count"] == 0
    assert report["summary"]["coverage_gate"]["status"] == "failed"


def test_highlight_plan_strategy_keeps_legacy_full_and_native_bounded(monkeypatch):
    calls = []

    def fake_has_llm(api_key, model):
        return True

    def fake_plan(scene_evidence, global_summary, full_subtitle_summary, api_key="", base_url="", model=""):
        calls.append(
            {
                "count": len(scene_evidence),
                "global_keys": set(global_summary.keys()),
                "full_keys": set(full_subtitle_summary.keys()),
            }
        )
        return {"selected_segment_ids": ["s1"]}

    monkeypatch.setattr("app.services.movie_story.highlight_runtime._has_real_llm_config", fake_has_llm)
    monkeypatch.setattr("app.services.movie_story.highlight_runtime.plan_story_highlights", fake_plan)

    evidence = [
        {"segment_id": f"s{i}", "start": i, "highlight_score": 100 - i}
        for i in range(20)
    ]
    global_summary = {"main_storyline": "x" * 3000, "extra_legacy_key": "kept"}
    full_summary = {"highlight_windows": [{"start": 0, "end": 1}], "extra_legacy_key": "kept"}

    legacy_plan = _safe_plan_story_highlights(
        evidence,
        global_summary=global_summary,
        full_subtitle_understanding=full_summary,
        allow_llm=True,
        api_key="key",
        base_url="url",
        model="model",
        scene_overrides={"movie_story_strategy": "legacy_understanding", "movie_story_highlight_plan_max_candidates": 8},
    )
    native_plan = _safe_plan_story_highlights(
        evidence,
        global_summary=global_summary,
        full_subtitle_understanding=full_summary,
        allow_llm=True,
        api_key="key",
        base_url="url",
        model="model",
        scene_overrides={"movie_story_strategy": "native_runtime", "movie_story_highlight_plan_max_candidates": 8},
    )

    assert legacy_plan["plan_policy"] == "legacy_llm_full_understanding_plan"
    assert native_plan["plan_policy"] == "native_llm_capped_ranked_compact_plan"
    assert calls[0]["count"] == 20
    assert calls[1]["count"] == 8
    assert "extra_legacy_key" in calls[0]["global_keys"]
    assert "extra_legacy_key" not in calls[1]["global_keys"]
