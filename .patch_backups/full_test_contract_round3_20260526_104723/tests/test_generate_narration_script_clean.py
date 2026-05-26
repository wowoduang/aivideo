import unittest
import json

import app.services.generate_narration_script_clean as narration_clean


class GenerateNarrationScriptCleanTests(unittest.TestCase):
    def test_historical_drama_template_is_loaded_from_json_library(self):
        templates = narration_clean._load_narration_style_templates()

        self.assertIn("historical_drama", templates)
        rendered = narration_clean._style_template_directive("historical_drama")
        self.assertIn("历史正剧深度解说｜通用AI提示词模板", rendered)
        self.assertIn("二、剪辑格式规范（最人性化、剪辑专用）", rendered)
        self.assertIn("先保证能剪出来", rendered)
        self.assertNotIn("五、", rendered)
        self.assertNotIn("六、", rendered)

    def test_historical_drama_style_guide_includes_direct_prompt_template(self):
        guide = narration_clean._build_style_guide("historical_drama", "历史宫廷")

        self.assertIn("历史正剧深度解说｜通用AI提示词模板", guide)
        self.assertIn("让解说词回来后能直接按时间区间切画面", guide)
        self.assertIn("禁止做大跨度累计合并、禁止整段超长时间块", guide)
        self.assertIn("单段时间区间控制在40秒—90秒，最大不超过2分钟", guide)
        self.assertIn("朱元璋同款冷沉写实风", guide)

    def test_historical_drama_forbidden_words_are_caught_as_cliche(self):
        self.assertTrue(narration_clean._has_analysis_cliche("天灾无情撕开时代伤疤，浮沉乱世看透冰冷人性。"))

    def test_historical_drama_fast_cut_merges_tiny_evidence_windows(self):
        evidence = [
            {
                "segment_id": f"s{i:02d}",
                "start": float(i * 10),
                "end": float(i * 10 + 10),
                "main_text_evidence": f"第{i}段字幕",
                "llm_highlight_selected": True,
                "highlight_filter_selected": True,
            }
            for i in range(12)
        ]

        packages = narration_clean._prepare_narration_packages(evidence, "historical_drama")

        self.assertLess(len(packages), len(evidence))
        self.assertEqual("historical_fast_cut_001", packages[0]["segment_id"])
        self.assertTrue(packages[0]["historical_fast_cut"])
        self.assertGreaterEqual(packages[0]["duration"], 40)
        self.assertLessEqual(packages[0]["duration"], 90)
        self.assertTrue(all(pkg["duration"] <= 120 for pkg in packages))
        self.assertIn("s00", packages[0]["source_segment_ids"])

    def test_historical_drama_prompt_keeps_whole_subtitle_timeline_for_understanding(self):
        evidence = [
            {
                "segment_id": f"s{i:02d}",
                "start": float(i * 10),
                "end": float(i * 10 + 10),
                "main_text_evidence": f"整集字幕原文{i}",
            }
            for i in range(8)
        ]
        packages = narration_clean._prepare_narration_packages(evidence, "historical_drama")

        prompt = narration_clean._build_full_subtitle_narration_prompt(
            packages,
            source_evidence=evidence,
            global_summary={},
            project_context={"timeline_rule": "字幕时间去切原片"},
            style_guide=narration_clean._build_style_guide("historical_drama", "历史宫廷"),
            style_examples="",
            strategy_profile={},
            total_char_budget=800,
        )

        self.assertIn("整集原始字幕时间轴", prompt)
        self.assertIn("整集字幕原文0", prompt)
        self.assertIn("整集字幕原文7", prompt)
        self.assertIn("historical_fast_cut_001", prompt)
        self.assertIn("后续直接用这些字幕时间切原片", prompt)

    def test_historical_drama_generation_direct_cuts_without_llm(self):
        original = narration_clean._call_chat_completion
        calls = []

        def fake_call(prompt, api_key="", base_url="", model="", timeout=90):
            calls.append(prompt)
            return json.dumps({"items": []}, ensure_ascii=False)

        narration_clean._call_chat_completion = fake_call
        try:
            items = narration_clean.generate_narration_from_scene_evidence(
                [
                    {"segment_id": f"s{i:02d}", "start": float(i * 10), "end": float(i * 10 + 10), "main_text_evidence": f"字幕{i}"}
                    for i in range(8)
                ],
                api_key="key",
                base_url="",
                model="model",
                style="historical_drama",
            )
        finally:
            narration_clean._call_chat_completion = original

        self.assertEqual([], calls)
        self.assertTrue(items)
        self.assertTrue(all(item["direct_cut_first"] for item in items))
        self.assertTrue(all(item["OST"] == 1 for item in items))
        self.assertTrue(all(item["composition_audio_mode"] == "raw" for item in items))
        self.assertTrue(all(item["llm_raw_voice_keep"] for item in items))
        self.assertTrue(all(item["raw_voice_retain_suggestion"] for item in items))
        self.assertTrue(all(item["highlight_filter_selected"] for item in items))
        self.assertTrue(all(item["narration"] == "" for item in items))
        self.assertGreaterEqual(items[0]["duration"], 40)

    def test_pick_ost_forces_opening_segment_to_use_narration(self):
        pkg = {
            "start": 0.0,
            "end": 8.0,
            "importance_level": "high",
            "plot_function": "铺垫",
            "llm_raw_voice_keep": True,
            "audio_strategy": "keep",
            "is_opening_segment": True,
        }

        ost = narration_clean._pick_ost(pkg, {"raw_voice_keep": True})

        self.assertEqual(2, ost)

    def test_pick_ost_prefers_narration_for_long_raw_voice_segments(self):
        pkg = {
            "start": 260.25,
            "end": 305.75,
            "importance_level": "high",
            "plot_function": "信息揭露",
            "llm_raw_voice_keep": True,
            "audio_strategy": "keep",
        }

        ost = narration_clean._pick_ost(pkg, {"raw_voice_keep": True})

        self.assertEqual(2, ost)

    def test_trim_script_overlaps_moves_following_segment_start_forward(self):
        items = [
            {
                "_id": 1,
                "start": 260.25,
                "end": 305.75,
                "timestamp": "00:04:20,250-00:05:05,750",
                "source_timestamp": "00:04:20,250-00:05:05,750",
                "narration": "第一段",
            },
            {
                "_id": 2,
                "start": 279.167,
                "end": 360.5,
                "timestamp": "00:04:39,167-00:06:00,500",
                "source_timestamp": "00:04:39,167-00:06:00,500",
                "narration": "第二段",
            },
        ]

        trimmed = narration_clean._trim_script_overlaps(items)

        self.assertEqual(2, len(trimmed))
        self.assertEqual(305.75, trimmed[1]["start"])
        self.assertEqual(54.75, trimmed[1]["duration"])
        self.assertEqual("00:05:05,750-00:06:00,500", trimmed[1]["timestamp"])

    def test_timecode_strings_are_accepted_in_script_timing(self):
        item = narration_clean._build_script_item(
            1,
            {
                "segment_id": "s1",
                "start": "00:08:41,018",
                "end": "00:08:45,518",
                "main_text_evidence": "众人沉默下来，局势开始变紧。",
            },
            {"narration": "众人这一沉默，让局势一下子绷紧了。"},
            "",
            {},
            "general",
        )

        self.assertEqual(521.018, item["start"])
        self.assertEqual(525.518, item["end"])
        self.assertEqual("00:08:41,018-00:08:45,518", item["timestamp"])

    def test_clean_review_rewrite_hint_strips_meta_prefix(self):
        cleaned = narration_clean._clean_review_rewrite_hint(
            '如果需要更保守，可以修改为：“守城战已经打响，现场一片紧张。”'
        )

        self.assertEqual("守城战已经打响，现场一片紧张。", cleaned)

    def test_resolve_review_narration_text_keeps_original_when_hint_is_meta(self):
        result = narration_clean._resolve_review_narration_text(
            "守城战已经打响，士兵正在死守。",
            {"safe_rewrite_hint": "建议改为：如果想更保守，可以换个说法"},
            40,
        )

        self.assertEqual("守城战已经打响，士兵正在死守。", result)

    def test_soften_uncertain_speaker_attribution_replaces_role_guess(self):
        softened = narration_clean._soften_uncertain_speaker_attribution(
            "皇上说先把人押下去，太监回应得很快。",
            {
                "speaker_names": [],
                "speaker_turns": 2,
            },
        )

        self.assertEqual("有人说先把人押下去，有人回应得很快。", softened)

    def test_postprocess_candidate_narration_adds_opening_prefix(self):
        narration = narration_clean._postprocess_candidate_narration(
            "局势一下子就紧了起来。",
            {
                "is_opening_segment": True,
                "speaker_names": [],
                "speaker_turns": 0,
            },
            40,
            "general",
        )

        self.assertTrue(narration.startswith("故事一开场，"))

    def test_local_fallback_avoids_analysis_cliche(self):
        narration = narration_clean._local_commentary_narration(
            {
                "start": 0.0,
                "end": 10.0,
                "plot_function": "信息揭露",
                "importance_level": "high",
                "main_text_evidence": "官差催征税银，饥民无粮可交，仍被说成抗税。",
            },
            "general",
            120,
        )

        banned = ("这一段主要交代", "这一段承担的是", "信息揭露功能", "推动矛盾升级")
        self.assertFalse(any(token in narration for token in banned), narration)

    def test_build_script_item_rejects_analysis_cliche(self):
        with self.assertRaises(ValueError):
            narration_clean._build_script_item(
                1,
                {
                    "start": 0.0,
                    "end": 10.0,
                    "plot_function": "信息揭露",
                    "importance_level": "high",
                    "main_text_evidence": "官差催征税银，饥民无粮可交，仍被说成抗税。",
                },
                {"narration": "这一段主要交代，皇权把催税压力继续往下压。"},
                "",
                {},
                "general",
            )

    def test_postprocess_script_items_rejects_duplicate_narration(self):
        items = [
            {
                "_id": 1,
                "start": 0.0,
                "end": 8.0,
                "duration": 8.0,
                "timestamp": "00:00:00,000-00:00:08,000",
                "narration": "孩子们嘴里的皇帝，没有天下和权谋，只有吃不完的大饼和面馍。",
                "main_text_evidence": "孩子们说皇上能吃大饼和面馍。",
                "char_budget": 80,
            },
            {
                "_id": 2,
                "start": 8.0,
                "end": 16.0,
                "duration": 8.0,
                "timestamp": "00:00:08,000-00:00:16,000",
                "narration": "孩子们嘴里的皇帝，没有天下和权谋，只有吃不完的大饼和面馍。",
                "main_text_evidence": "孩子们说皇上能吃大饼和面馍。",
                "char_budget": 80,
            },
        ]

        with self.assertRaises(ValueError):
            narration_clean._postprocess_script_items(items)

    def test_generate_narration_prefers_full_subtitle_batch(self):
        calls = []
        original = narration_clean._call_chat_completion

        def fake_call(prompt, api_key="", base_url="", model="", timeout=90):
            calls.append(prompt)
            if "按时间轴排列的字幕/画面证据" in prompt:
                return json.dumps(
                    {
                        "items": [
                            {"segment_id": "s1", "order": 1, "narration": "官府逼到门前，朱家已经没有多少余地。"},
                            {
                                "segment_id": "s2",
                                "order": 2,
                                "narration": "孩子们说起皇帝，想的其实只是能吃饱。",
                                "sentences": [
                                    {
                                        "sentence_id": "s2_01",
                                        "text": "孩子们说起皇帝，想的其实只是能吃饱。",
                                        "start": 8.0,
                                        "end": 16.0,
                                    }
                                ],
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            return json.dumps({"status": "pass"}, ensure_ascii=False)

        narration_clean._call_chat_completion = fake_call
        try:
            items = narration_clean.generate_narration_from_scene_evidence(
                [
                    {"segment_id": "s1", "start": 0.0, "end": 8.0, "main_text_evidence": "官差催税，朱家无钱。"},
                    {"segment_id": "s2", "start": 8.0, "end": 16.0, "main_text_evidence": "孩子们说皇上能吃大饼。"},
                ],
                api_key="key",
                base_url="",
                model="model",
                style="general",
            )
        finally:
            narration_clean._call_chat_completion = original

        self.assertEqual("故事一开场，官府逼到门前，朱家已经没有多少余地。", items[0]["narration"])
        self.assertEqual("孩子们说起皇帝，想的其实只是能吃饱。", items[1]["narration"])
        self.assertEqual("s2_01", items[1]["narration_sentences"][0]["sentence_id"])
        self.assertEqual(5, len(calls))  # three strategy candidates + two validation calls
        self.assertIn("按时间轴排列的字幕/画面证据", calls[0])


    def test_missing_batch_narration_uses_original_audio(self):
        original = narration_clean._call_chat_completion

        def fake_call(prompt, api_key="", base_url="", model="", timeout=90):
            if "timeline_json" in prompt or "segment_id" in prompt:
                return json.dumps(
                    {"items": [{"segment_id": "s1", "order": 1, "narration": "官府逼到门前，朱家已经没有多少余地。"}]},
                    ensure_ascii=False,
                )
            return json.dumps({"status": "pass"}, ensure_ascii=False)

        narration_clean._call_chat_completion = fake_call
        try:
            items = narration_clean.generate_narration_from_scene_evidence(
                [
                    {"segment_id": "s1", "start": 0.0, "end": 8.0, "main_text_evidence": "官差催税，朱家无钱。"},
                    {"segment_id": "s2", "start": 8.0, "end": 16.0, "main_text_evidence": "孩子们说皇上能吃大饼。"},
                ],
                api_key="key",
                base_url="",
                model="model",
                style="general",
            )
        finally:
            narration_clean._call_chat_completion = original

        self.assertEqual("s2", items[1]["segment_id"])
        self.assertEqual("", items[1]["narration"])
        self.assertEqual(1, items[1]["OST"])
        self.assertEqual("raw", items[1]["composition_audio_mode"])
        self.assertTrue(items[1]["narration_missing_use_original_audio"])

    def test_template_cliche_narration_uses_original_audio(self):
        original = narration_clean._call_chat_completion

        def fake_call(prompt, api_key="", base_url="", model="", timeout=90):
            if "segment_id" in prompt:
                return json.dumps(
                    {"items": [{"segment_id": "s1", "order": 1, "narration": "话说到这里，真正麻烦的事还在后面。"}]},
                    ensure_ascii=False,
                )
            return json.dumps({"status": "pass"}, ensure_ascii=False)

        narration_clean._call_chat_completion = fake_call
        try:
            items = narration_clean.generate_narration_from_scene_evidence(
                [{"segment_id": "s1", "start": 0.0, "end": 8.0, "main_text_evidence": "官差进屋搜缴。"}],
                api_key="key",
                base_url="",
                model="model",
                style="general",
            )
        finally:
            narration_clean._call_chat_completion = original

        self.assertEqual("", items[0]["narration"])
        self.assertEqual(1, items[0]["OST"])
        self.assertTrue(items[0]["narration_quality_rejected_to_original_audio"])


if __name__ == "__main__":
    unittest.main()
