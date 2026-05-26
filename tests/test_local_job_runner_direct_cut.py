from app.services import local_job_runner


def test_direct_cut_movie_story_result_auto_composes_video(monkeypatch):
    calls = {}

    def fake_run_video(task_id, params):
        calls["task_id"] = task_id
        calls["params"] = params
        return {"videos": ["out.mp4"], "combined_videos": ["merged.mp4"]}

    monkeypatch.setattr(local_job_runner, "_run_video_job", fake_run_video)
    monkeypatch.setattr(local_job_runner, "_update_processing_state", lambda *args, **kwargs: None)

    result = local_job_runner._compose_direct_cut_movie_story_result(
        "task-1",
        {"video_path": "source.mp4"},
        {
            "success": True,
            "direct_cut_first": True,
            "highlight_script_path": "script.json",
            "script_items": [{"_id": 1, "OST": 1, "direct_cut_first": True}],
        },
    )

    assert result["direct_cut_video_composed"] is True
    assert result["videos"] == ["out.mp4"]
    assert result["combined_videos"] == ["merged.mp4"]
    assert calls["task_id"] == "task-1"
    assert calls["params"].video_origin_path == "source.mp4"
    assert calls["params"].video_clip_json_path == "script.json"
    assert calls["params"].subtitle_enabled is False
