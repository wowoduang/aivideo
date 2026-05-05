import unittest

from app.services.movie_story.highlight_edit_selection import (
    build_highlight_recut_selection_pool,
    detect_main_character_reference,
    merge_unique_clips,
)


class MovieStoryHighlightEditSelectionTests(unittest.TestCase):
    def test_direct_selection_pool_keeps_anchor_and_character_reasons(self):
        clips = [
            {
                "clip_id": "opening",
                "start": 0.0,
                "end": 5.0,
                "duration": 5.0,
                "source": "hybrid",
                "story_position": 0.03,
                "story_stage_hint": "opening",
                "story_score": 0.7,
                "emotion_score": 0.5,
                "energy_score": 0.5,
                "total_score": 0.66,
                "character_names": ["Hero"],
                "speaker_names": ["Hero"],
                "selection_reason": [],
            },
            {
                "clip_id": "climax",
                "start": 30.0,
                "end": 36.0,
                "duration": 6.0,
                "source": "scene",
                "story_position": 0.62,
                "story_stage_hint": "climax",
                "story_score": 0.9,
                "emotion_score": 0.85,
                "energy_score": 0.8,
                "total_score": 0.86,
                "raw_audio_worthy": True,
                "character_names": ["Hero"],
                "speaker_names": ["Hero"],
                "selection_reason": [],
            },
        ]

        selected = build_highlight_recut_selection_pool(clips, target_duration_seconds=70)
        by_id = {item["clip_id"]: item for item in selected}

        self.assertIn("opening", by_id)
        self.assertIn("climax", by_id)
        self.assertIn("opening_anchor", by_id["opening"]["selection_reason"])
        self.assertIn("raw_audio_anchor", by_id["climax"]["selection_reason"])
        self.assertEqual(detect_main_character_reference(clips), ["Hero"])

    def test_merge_unique_clips_preserves_specific_scene_metadata(self):
        merged = merge_unique_clips(
            [
                {
                    "clip_id": "plot_a",
                    "start": 10.0,
                    "end": 16.0,
                    "source": "hybrid",
                    "total_score": 0.6,
                    "selection_reason": ["coverage_anchor"],
                    "character_names": ["A"],
                }
            ],
            [
                {
                    "clip_id": "scene_a",
                    "start": 10.2,
                    "end": 15.8,
                    "source": "scene",
                    "total_score": 0.75,
                    "raw_audio_worthy": True,
                    "selection_reason": ["scene_anchor"],
                    "character_names": ["B"],
                    "keyframe_candidates": [12.0],
                }
            ],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "scene")
        self.assertTrue(merged[0]["raw_audio_worthy"])
        self.assertIn("coverage_anchor", merged[0]["selection_reason"])
        self.assertIn("scene_anchor", merged[0]["selection_reason"])
        self.assertEqual(merged[0]["character_names"], ["A", "B"])
        self.assertEqual(merged[0]["keyframe_candidates"], [12.0])


if __name__ == "__main__":
    unittest.main()
