from app.services.timeline_allocator import apply_timeline_budget, trim_text_to_budget


def test_trim_text_to_budget_never_exceeds_budget_when_punctuation_is_appended():
    trimmed = trim_text_to_budget("这是一段会超过预算的长旁白文本", 8)

    assert len(trimmed) <= 8


def test_apply_timeline_budget_auto_trim_clears_overflow_error():
    items = [{"scene_id": "plot_016", "start": 0.0, "end": 6.2, "narration": "这是一段会超过预算的长旁白文本"}]

    [item] = apply_timeline_budget(items, chars_per_second=1.0, reserve_ratio=1.0)

    assert len(item["narration"]) <= item["char_budget"]
    assert item["fit_check"]["severity"] == "ok"
