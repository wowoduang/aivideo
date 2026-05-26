from app.services.movie_story.stage3_highlight_selection import select_highlights_with_report


def _seg(i, start, end, text, plot="发展", drop=False, reason=""):
    return {
        "candidate_id": f"c_{i:03d}",
        "candidate_type": "scene",
        "video_start": float(start),
        "video_end": float(end),
        "subtitle_text": text,
        "plot_function": plot,
        "importance_level": "medium",
        "information_tags": ["信息增量"] if i % 2 == 0 else [],
        "emotion_tags": ["紧张"] if i % 3 == 0 else [],
        "character_trace": {"focus_character": "男主", "key_action": "继续调查"},
        "drop_suggestion": drop,
        "drop_reason": reason,
    }


def test_highlight_selection_uses_coverage_fallback_when_initial_selection_is_too_short():
    # 20 valid 15-second candidates are enough to satisfy a 5-minute target's
    # balanced hard minimum (135s) and preferred minimum (225s). A strategy that
    # only picks the top couple of clips would fail this gate.
    evidence = [_seg(i, i * 20, i * 20 + 15, "男主发现秘密，冲突升级，决定继续调查。") for i in range(20)]
    # Add hard drops that should not be used to pad coverage.
    evidence += [_seg(100 + i, 500 + i * 20, 510 + i * 20, "片尾 演职员表", drop=True, reason="片尾字幕") for i in range(3)]

    report = select_highlights_with_report(evidence, target_minutes=5, highlight_selectivity="balanced")
    summary = report["summary"]

    assert summary["selected_total_duration"] >= summary["hard_min_seconds"]
    assert summary["coverage_gate"]["status"] in {"passed", "warning"}
    assert summary["coverage_gate"]["repair_action"] in {"coverage_fallback_selection", "none"}
    assert all("片尾" not in h.source_segment.get("subtitle_text", "") for h in report["selected_highlights"])
    assert summary["flow_success_gates"]


def test_very_loose_keeps_story_material_and_reports_success_gates():
    evidence = [_seg(i, i * 12, i * 12 + 10, "女主怀疑真相，人物关系发生变化。", plot="关系变化") for i in range(12)]
    report = select_highlights_with_report(evidence, target_minutes=2, highlight_selectivity="very_loose")
    summary = report["summary"]

    assert len(report["selected_highlights"]) >= 9
    assert summary["coverage_gate"]["ok"] is True
    assert summary["overall_ok"] is True
    assert summary["policy"].startswith("stage3_is_the_only_stage")
