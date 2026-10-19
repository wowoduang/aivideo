from app.services.generate_narration_script import (
    generate_narration_from_scene_evidence,
    _is_verbatim_like,
)
import pytest


def test_local_narration_is_not_subtitle_recitation_for_movie_story_highlights():
    evidence = [
        {
            "segment_id": "h1",
            "highlight_id": "h1",
            "scene_id": "h1",
            "start": 179.36,
            "end": 186.08,
            "timestamp": "00:02:59,360-00:03:06,080",
            "subtitle_text": "诺，皇上，再过两个月可臣妾的生日了",
            "main_text_evidence": "诺，皇上，再过两个月可臣妾的生日了",
            "plot_function": "信息揭露",
            "importance_level": "medium",
            "_global_summary": {"protagonist": "朱重八"},
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
        },
        {
            "segment_id": "h2",
            "highlight_id": "h2",
            "scene_id": "h2",
            "start": 186.08,
            "end": 195.56,
            "timestamp": "00:03:06,080-00:03:15,560",
            "subtitle_text": "朕现在就任命你为钦差大臣，赴各地催征税银 皇上，可如今遍地饥民，岂是抗税",
            "main_text_evidence": "朕现在就任命你为钦差大臣，赴各地催征税银 皇上，可如今遍地饥民，岂是抗税",
            "plot_function": "冲突升级",
            "importance_level": "high",
            "_global_summary": {"protagonist": "朱重八"},
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
        },
    ]
    items = generate_narration_from_scene_evidence(
        evidence,
        api_key="",
        base_url="",
        model="",
        style="short_drama",
        video_title="朱元璋",
    )

    assert items
    assert all(item.get("composition_audio_mode") == "raw" for item in items)
    assert all(item.get("narration", "") == "" for item in items)
    assert all(not _is_verbatim_like(item.get("narration", ""), item) for item in items)


def test_verbatim_detector_rejects_raw_dialogue_copy():
    pkg = {"subtitle_text": "朕现在就任命你为钦差大臣，赴各地催征税银"}
    assert _is_verbatim_like("朕现在就任命你为钦差大臣，赴各地催征税银", pkg)
    assert not _is_verbatim_like("皇权把催税压力继续往下压，朝廷和百姓的矛盾被撕开。", pkg)
