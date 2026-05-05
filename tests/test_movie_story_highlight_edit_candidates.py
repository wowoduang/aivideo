from app.services.movie_story import highlight_edit_candidates as candidates


def test_scene_candidates_keep_dialogue_signals_and_pressure_direction():
    scene_candidates = candidates.build_scene_candidates(
        scene_segments=[
            {
                "scene_id": "scene_002",
                "start": 10.0,
                "end": 16.5,
                "subtitle_ids": ["sub_101", "sub_102", "sub_103", "sub_104"],
                "subtitle_text": "你说 我没什么可说的 你还想装到什么时候 我真的没骗你们",
            }
        ],
        plot_chunks=[],
        video_boundary_candidates=[],
        subtitle_segments=[
            {"seg_id": "sub_101", "speaker": "张三", "text": "你说"},
            {"seg_id": "sub_102", "speaker": "王五", "text": "我没什么可说的"},
            {"seg_id": "sub_103", "speaker": "李四", "text": "你还想装到什么时候"},
            {"seg_id": "sub_104", "speaker": "王五", "text": "我真的没骗你们"},
        ],
    )

    assert len(scene_candidates) == 1
    item = scene_candidates[0]
    assert item["speaker_names"] == ["张三", "李四", "王五"]
    assert item["speaker_sequence"] == ["张三", "王五", "李四", "王五"]
    assert item["pressure_target_names"] == ["王五"]
    assert item["pressure_source_names"] == ["张三", "李四"]
    assert item["group_reaction_score"] > 0.7


def test_narrated_clip_pool_uses_selection_runtime_without_name_error():
    base_clip = {
        "clip_id": "clip_001",
        "start": 1.0,
        "end": 7.0,
        "duration": 6.0,
        "source": "plot",
        "story_position": 0.2,
        "story_stage_hint": "setup",
        "total_score": 0.8,
        "story_score": 0.7,
        "emotion_score": 0.6,
        "energy_score": 0.5,
        "raw_audio_worthy": True,
        "subtitle_text": "主角发现了异常",
        "selection_reason": ["score_pick"],
        "tags": ["reveal"],
    }
    scene_clip = dict(base_clip, clip_id="scene_clip_001", source="scene", start=7.2, end=10.0, duration=2.8)

    pool = candidates.build_narrated_clip_pool(
        [base_clip],
        [scene_clip],
        narration_units=[{"text": "主角终于发现异常。"}],
        target_duration_seconds=30,
    )

    assert pool
    assert {item["clip_id"] for item in pool} >= {"clip_001", "scene_clip_001"}
