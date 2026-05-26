from app.services.movie_story.human_narration import build_human_narration_package, get_style_profile
from app.services.movie_story.human_narration.humanize_rewriter import humanize_text
from app.services.movie_story.human_narration.transition_writer import generate_transitions
from app.services.movie_story.production import check_video_plan_quality, design_subtitle_cues


def sample_highlights():
    return [
        {
            "highlight_id": "h_001",
            "source_candidate_id": "story_001",
            "video_start": 10.0,
            "video_end": 25.0,
            "plot_function": "信息揭露",
            "subtitle_text": "男主发现关键证据 真相开始浮出水面",
            "scores": {"highlight_score": 0.86, "information_score": 0.9, "character_score": 0.6},
            "character_trace": {"focus_character": "男主", "goal_change_hint": True},
        },
        {
            "highlight_id": "h_002",
            "source_candidate_id": "story_002",
            "video_start": 25.0,
            "video_end": 42.0,
            "plot_function": "冲突升级",
            "subtitle_text": "女主怀疑老板背叛 现场开始失控",
            "scores": {"highlight_score": 0.79, "emotion_score": 0.82, "character_score": 0.74},
            "character_trace": {"focus_character": "女主", "relationship_change_hint": True},
        },
        {
            "highlight_id": "h_003",
            "source_candidate_id": "story_003",
            "video_start": 42.0,
            "video_end": 55.0,
            "plot_function": "人物转折",
            "subtitle_text": "男主决定留下救人",
            "scores": {"highlight_score": 0.72, "character_score": 0.84},
            "character_trace": {"focus_character": "男主", "goal_change_hint": True},
        },
    ]


def test_style_profile_normalizes_chinese_alias():
    profile = get_style_profile("悬疑解说")
    assert profile["style_key"] == "suspense"
    assert "delivery" in profile


def test_human_narration_package_has_director_hooks_transitions_and_quality():
    package = build_human_narration_package(sample_highlights(), style_key="suspense")

    assert package["style_profile"]["style_key"] == "suspense"
    assert package["opening_hooks"]
    assert len(package["directed_segments"]) == 3
    assert package["directed_segments"][0]["narration_role"] == "hook_setup"
    assert len(package["transitions"]) == 2
    assert len(package["script_items"]) == 3
    assert "human_like_score" in package["quality_report"]
    assert package["principles"]["retiming"] == "human_narration_must_not_modify_video_start_video_end"


def test_humanize_text_removes_template_words_and_splits_long_sentence():
    text = "随后，男主发现事情并不简单，于是他决定继续调查，因此，整个事件开始发生变化。"
    out = humanize_text(text, style_key="suspense", max_sentence_len=16)
    assert "事情并不简单" not in out
    assert "因此" not in out
    assert "\n" in out


def test_transitions_bridge_adjacent_highlights():
    transitions = generate_transitions(sample_highlights())
    assert transitions[0]["from_segment"] == "h_001"
    assert transitions[0]["to_segment"] == "h_002"
    assert transitions[0]["text"]


def test_subtitle_designer_outputs_short_video_cues():
    package = build_human_narration_package(sample_highlights(), style_key="short_video_fast")
    cues = design_subtitle_cues(package["script_items"], max_chars_per_line=10)
    assert cues
    assert all(len(line) <= 13 for cue in cues for line in cue["lines"])
    assert cues[0]["style"] == "suspense_yellow_black"


def test_video_quality_gate_blocks_retiming_regression():
    highlights = sample_highlights()
    script_items = [
        {"segment_id": "h_001", "video_start": 10.0, "video_end": 25.0, "text": "正常"},
        {"segment_id": "h_002", "video_start": 24.0, "video_end": 42.0, "text": "和前段重叠"},
        {"segment_id": "h_003", "video_start": 42.0, "video_end": 58.0, "text": "被错误拉长"},
    ]
    report = check_video_plan_quality(script_items, source_highlights=highlights)
    codes = {issue["code"] for issue in report["issues"]}
    assert report["passed"] is False
    assert "overlap" in codes
    assert "video_time_changed_after_selection" in codes
