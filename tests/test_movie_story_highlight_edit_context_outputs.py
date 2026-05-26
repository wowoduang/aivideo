import json

from app.services.movie_story import highlight_edit_context as context
from app.services.movie_story import highlight_edit_outputs as outputs


def test_visual_signal_config_normalizes_unknown_mode_to_auto():
    auto = context.resolve_visual_signal_config("auto")
    boost = context.resolve_visual_signal_config("boost")
    unknown = context.resolve_visual_signal_config("unknown")

    assert unknown["mode"] == "auto"
    assert auto["enabled"] is True
    assert boost["boundary_args"]["threshold"] < auto["boundary_args"]["threshold"]


def test_select_clips_by_ids_marks_ai_and_raw_audio_reasons():
    selected = context.select_clips_by_ids(
        [
            {"clip_id": "a", "start": 0, "end": 3, "duration": 3, "selection_reason": ["score_pick"]},
            {"clip_id": "b", "start": 5, "end": 8, "duration": 3, "selection_reason": []},
        ],
        ["b", "missing", "a"],
        raw_audio_clip_ids=["a"],
    )

    assert [item["clip_id"] for item in selected] == ["b", "a"]
    assert "ai_selected" in selected[0]["selection_reason"]
    assert selected[1]["raw_audio_worthy"] is True
    assert "raw_audio_keep" in selected[1]["selection_reason"]


def test_refresh_narration_matches_from_planned_replaces_clip_window():
    refreshed = context.refresh_narration_matches_from_planned(
        [
            {
                "clip_id": "clip_1",
                "clip": {"clip_id": "clip_1", "start": 1.0, "end": 2.0},
            }
        ],
        [
            {
                "clip_id": "clip_1",
                "start": 10.0,
                "end": 13.5,
                "duration": 3.5,
            }
        ],
    )

    assert refreshed[0]["clip"]["start"] == 10.0
    assert refreshed[0]["clip_group"][0]["end"] == 13.5
    assert refreshed[0]["group_end"] == 13.5


def test_write_outputs_persists_plan_and_script_items(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs.utils, "script_dir", lambda: str(tmp_path))

    paths = outputs.write_outputs(
        "hash123",
        {"mode": "highlight_recut", "segments": [{"clip_id": "c1"}]},
        [{"clip_id": "c1", "start": 0.0, "end": 2.0}],
    )

    assert paths["composition_plan_path"].endswith(".json")
    assert paths["script_path"].endswith(".json")
    with open(paths["composition_plan_path"], "r", encoding="utf-8") as handle:
        plan = json.load(handle)
    with open(paths["script_path"], "r", encoding="utf-8") as handle:
        script_items = json.load(handle)
    assert plan["mode"] == "highlight_recut"
    assert script_items[0]["clip_id"] == "c1"


def test_build_success_response_keeps_public_keys():
    response = outputs.build_success_response(
        mode="highlight_recut",
        subtitle_result={"source": "mock"},
        subtitle_segments=[],
        scene_segments=[],
        video_boundary_candidates=[],
        plot_chunks=[],
        plot_candidate_clips=[],
        candidate_clips=[],
        scene_candidate_clips=[],
        candidate_stats={"merged_candidate_count": 0},
        highlight_profile={"id": "general"},
        highlight_capabilities={},
        selected_clips=[],
        narration_units=[],
        narration_matches=[],
        composition_plan={"segments": []},
        output_paths={"composition_plan_path": "plan.json", "script_path": "script.json"},
        script_items=[],
    )

    assert response["success"] is True
    assert response["composition_plan_path"] == "plan.json"
    assert response["script_path"] == "script.json"
    assert response["candidate_stats"]["merged_candidate_count"] == 0
