from app.services import task


def test_direct_cut_raw_script_detection_requires_empty_original_audio_segments():
    assert task._is_direct_cut_raw_script(
        [
            {
                "direct_cut_first": True,
                "OST": 1,
                "narration": "",
            }
        ]
    )

    assert not task._is_direct_cut_raw_script(
        [
            {
                "direct_cut_first": True,
                "OST": 0,
                "narration": "voiceover",
            }
        ]
    )
