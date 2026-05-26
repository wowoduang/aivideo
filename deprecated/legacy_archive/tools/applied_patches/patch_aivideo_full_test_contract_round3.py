# -*- coding: utf-8 -*-
from __future__ import annotations

"""Round 3 contract cleanup for aivideo after two_round_visual cleanup.

This patch does not change the two-round prompts and does not expand visual
capability.  It aligns stale tests/utilities with the current mainflow:
base two_round, two_round_visual, and multi-short-video product flow.
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str, *, apply: bool, actions: list[str], backup_root: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    old = _read(path)
    if old == text:
        return
    rel = path.relative_to(PROJECT)
    actions.append(f"modify: {rel}")
    if apply:
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(old, encoding="utf-8")
        path.write_text(text, encoding="utf-8", newline="\n")


def _replace(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected block not found: {label}")
    return text.replace(old, new)


def _patch_json_utils(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "app/utils/json_utils.py"
    new = '''# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger


def _strip_markdown_json_fence(value: str) -> str:
    """Return the JSON body when an LLM wraps JSON in a markdown fence."""

    match = re.fullmatch(r"```(?:json)?\\s*(.*?)\\s*```", value.strip(), re.DOTALL | re.IGNORECASE)
    if not match:
        return value
    return match.group(1).strip()


def parse_and_fix_json(json_string: str) -> Any:
    """Parse common LLM JSON variants used by legacy callers.

    This helper intentionally returns None when no safe repair works. It does
    not hide failures in production chains that require strict parsing; those
    callers should raise their own explicit errors after receiving None.
    """

    if not json_string or not str(json_string).strip():
        return None

    normalized = _strip_markdown_json_fence(str(json_string).strip())

    for candidate in (
        normalized,
        normalized.replace("{{", "{").replace("}}", "}"),
    ):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.debug("JSON 解析失败: {}", exc)

    json_match = re.search(r"```(?:json)?\\s*(.*?)\\s*```", str(json_string).strip(), re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError as exc:
            logger.debug("JSON fenced 内容解析失败: {}", exc)

    return None
'''
    _write(path, new, apply=apply, actions=actions, backup_root=backup_root)


def _patch_verify_tool(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "tools/verify_movie_story_migration_stage.py"
    text = _read(path)
    old = '''def _find_stage_manifest(audit_dir: Path, stage_name: str) -> Path | None:
    direct = audit_dir / stage_name / "manifest.json"
    if direct.exists():
        return direct
    # Accept the root of _movie_story_pipeline_audit_clips as well.
    candidates = sorted(audit_dir.glob(f"run_*/{stage_name}/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
'''
    new = '''def _find_stage_manifest(audit_dir: Path, stage_name: str) -> Path | None:
    """Find stage manifests across legacy and namespaced audit layouts.

    Current movie_story runtime stores active pipeline audit outputs under
    producer namespaces such as ``runtime/`` and maps some legacy names to
    explicit runtime names. The verifier accepts both layouts so migration
    checks can validate the current contract without reconnecting old output
    directories.
    """

    alias_map = {
        "04_global_story_context": ["04_runtime_story_context", "04_story_audit_global_context"],
        "05_selected_highlights": ["05_runtime_selected_highlight_candidates", "05_story_audit_selected_highlights"],
        "06_scene_evidence_for_narration": [
            "06_runtime_scene_evidence_for_narration",
            "06_story_audit_scene_evidence_for_narration",
        ],
        "06a_evidence_completeness": ["06a_runtime_evidence_completeness", "06a_story_audit_evidence_completeness"],
    }
    aliases = {stage_name, *alias_map.get(stage_name, [])}
    for alias in aliases:
        direct = audit_dir / alias / "manifest.json"
        if direct.exists():
            return direct
        for namespace in ("runtime", "story_audit"):
            namespaced = audit_dir / namespace / alias / "manifest.json"
            if namespaced.exists():
                return namespaced

    patterns: list[str] = []
    for alias in aliases:
        patterns.extend([
            f"run_*/{alias}/manifest.json",
            f"run_*/*/{alias}/manifest.json",
            f"*/{alias}/manifest.json",
        ])
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(audit_dir.glob(pattern))
    candidates = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
'''
    if old in text:
        text = text.replace(old, new)
    elif "04_story_audit_global_context" not in text:
        raise RuntimeError("verify tool already differs; manual review needed")
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_narration_finalize(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "app/services/movie_story/narration_finalize.py"
    text = _read(path)
    text = text.replace(
        "from app.services.movie_story.story_runtime import normalize_script_items_without_retiming",
        "from app.services.movie_story.story_runtime import normalize_list, normalize_script_items_without_retiming",
    )
    text = text.replace(
        "from app.services.movie_story.story_runtime import normalize_list\n",
        "from app.services.movie_story.story_runtime import normalize_list, normalize_script_items_without_retiming\n",
    )
    text = text.replace(
        "return normalize_script_items_without_retiming(out)",
        "return normalize_list(out, candidate_type=\"script_item\")",
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_clip_and_subtitle_tests(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "tests/test_clip_and_merger_validation.py"
    text = _read(path)
    text = text.replace('patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=0)),', 'patch.object(module, "run_cancellable", return_value=SimpleNamespace(returncode=0)),')
    text = text.replace('patch.object(module.subprocess, "run", side_effect=fake_run),', 'patch.object(module, "run_cancellable", side_effect=fake_run),')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_subtitle_external.py"
    text = _read(path)
    text = text.replace('"app.services.subtitle_external.subprocess.run",', '"app.services.subtitle_external.run_cancellable",')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_generate_narration_tests(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "tests/test_generate_narration_script_clean.py"
    text = _read(path)
    text = text.replace(
        'self.assertIn("历史正剧深度解说｜通用AI提示词模板", rendered)\n        self.assertIn("二、剪辑格式规范（最人性化、剪辑专用）", rendered)\n        self.assertIn("先保证能剪出来", rendered)\n        self.assertNotIn("五、", rendered)\n        self.assertNotIn("六、", rendered)',
        'self.assertIn("双轮结构分析写实解说｜SRT先分析后写作", rendered)\n        self.assertIn("第一轮：读取原始SRT，只做结构分析", rendered)\n        self.assertIn("正式提示词在 app/services/movie_story/two_round_narration.py", rendered)',
    )
    text = text.replace(
        'self.assertIn("历史正剧深度解说｜通用AI提示词模板", guide)\n        self.assertIn("让解说词回来后能直接按时间区间切画面", guide)\n        self.assertIn("禁止做大跨度累计合并、禁止整段超长时间块", guide)\n        self.assertIn("单段时间区间控制在40秒—90秒，最大不超过2分钟", guide)\n        self.assertIn("朱元璋同款冷沉写实风", guide)',
        'self.assertIn("历史正剧冷沉写实风", guide)\n        self.assertIn("双轮结构分析写实解说｜SRT先分析后写作", guide)\n        self.assertIn("第一轮：读取原始SRT，只做结构分析", guide)',
    )
    text = text.replace('def test_historical_drama_generation_direct_cuts_without_llm(self):', 'def test_historical_drama_generation_direct_cuts_when_llm_parse_fails(self):')
    text = text.replace(
        'self.assertEqual([], calls)\n        self.assertTrue(items)',
        'self.assertEqual(1, len(calls))\n        self.assertIn("【带时间戳的原版字幕】", calls[0])\n        self.assertTrue(items)',
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_engine_tests(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "tests/test_movie_story_engine_boundary.py"
    text = _read(path)
    if "import pytest" not in text:
        text = text.replace("import types\n", "import types\n\nimport pytest\n")
    text = text.replace(
        '''def test_movie_story_policy_auto_defaults_to_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True
    assert decision.reason == "auto_selected_native"''',
        '''def test_movie_story_policy_auto_keeps_old_mainflow_inactive():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_LEGACY
    assert decision.native_ready is False
    assert decision.reason == "auto_fallback_legacy_until_native_ready"''',
    )
    text = text.replace(
        '''def test_legacy_movie_story_engine_keeps_old_call_shape(monkeypatch):
    captured = {}

    def fake_movie_story_pipeline(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [{"text": "demo"}]}

    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=fake_movie_story_pipeline)
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    payload = run_movie_story_engine(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        engine_backend="legacy",
        scene_overrides={"target_duration_minutes": 6},
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "legacy"
    assert payload["engine_backend_info"]["compatibility_engine"] == "subtitle_first_pipeline"
    assert "engine_backend" not in captured
    assert captured["scene_overrides"]["target_duration_minutes"] == 6''',
        '''def test_legacy_movie_story_engine_is_blocked_from_current_mainflow(monkeypatch):
    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=lambda **kwargs: {"success": True})
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    with pytest.raises(RuntimeError, match="old Native/Legacy mainflow is disabled"):
        run_movie_story_engine(
            video_path="demo.mp4",
            subtitle_path="demo.srt",
            engine_backend="legacy",
            scene_overrides={"target_duration_minutes": 6},
        )''',
    )
    text = text.replace(
        '''def test_scene_overrides_engine_backend_is_stripped(monkeypatch):
    captured = {}

    def fake_movie_story_pipeline(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": []}

    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=fake_movie_story_pipeline)
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    payload = run_movie_story_engine(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        scene_overrides={"engine_backend": "legacy", "target_duration_minutes": 5},
    )

    assert payload["success"] is True
    assert "engine_backend" not in captured["scene_overrides"]
    assert captured["scene_overrides"]["target_duration_minutes"] == 5''',
        '''def test_scene_overrides_engine_backend_cannot_reenable_old_movie_story_mainflow(monkeypatch):
    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=lambda **kwargs: {"success": True})
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    with pytest.raises(RuntimeError, match="old Native/Legacy mainflow is disabled"):
        run_movie_story_engine(
            video_path="demo.mp4",
            subtitle_path="demo.srt",
            scene_overrides={"engine_backend": "legacy", "target_duration_minutes": 5},
        )''',
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_engine_status.py"
    text = _read(path)
    text = text.replace('def test_engine_status_reports_native_backends_ready():', 'def test_engine_status_reports_current_backend_readiness():')
    text = text.replace(
        'assert status["native_ready"]["movie_story"] is True\n    assert status["native_ready"]["highlight_edit"] is True\n    assert status["engines"]["movie_story"]["selected_backend"] == "native"\n    assert status["engines"]["highlight_edit"]["selected_backend"] == "native"',
        'assert status["native_ready"]["movie_story"] is False\n    assert status["native_ready"]["highlight_edit"] is True\n    assert status["engines"]["movie_story"]["selected_backend"] == "legacy"\n    assert status["engines"]["highlight_edit"]["selected_backend"] == "native"',
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_native_highlight_engine.py"
    text = _read(path)
    text = text.replace(
        '''def test_movie_story_policy_now_selects_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE''',
        '''def test_movie_story_policy_keeps_old_native_mainflow_inactive():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_LEGACY
    assert decision.native_ready is False''',
    )
    text = text.replace('    assert decision.native_ready is False\n    assert decision.native_ready is True\n', '    assert decision.native_ready is False\n')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_native_movie_story_engine.py"
    text = _read(path)
    if "import pytest" not in text:
        text = text.replace("import shutil\n", "import shutil\n\nimport pytest\n")
    text = text.replace(
        '''def test_movie_story_native_policy_is_ready():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True''',
        '''def test_movie_story_native_policy_is_not_current_mainflow():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_LEGACY
    assert decision.native_ready is False''',
    )
    text = text.replace(
        'def test_legacy_understanding_highlight_mode_uses_old_finalize_path(monkeypatch):',
        '@pytest.mark.skip(reason="old native movie_story finalize path is archived; current mainflows are two_round/two_round_visual/multi_short_video")\ndef test_legacy_understanding_highlight_mode_uses_old_finalize_path(monkeypatch):',
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_audit_stage_tests(apply: bool, actions: list[str], backup_root: Path) -> None:
    helper = '''\n\ndef _stage_dir(audit_dir, stage_name):\n    rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))\n    for row in rows:\n        if row.get("source_stage") == stage_name or str(row.get("stage", "")).endswith("/" + stage_name):\n            return Path(row["dir"])\n    alias = {\n        "05_selected_highlights": "05_runtime_selected_highlight_candidates",\n        "06_scene_evidence_for_narration": "06_runtime_scene_evidence_for_narration",\n    }.get(stage_name, stage_name)\n    for row in rows:\n        if str(row.get("stage", "")).endswith("/" + alias):\n            return Path(row["dir"])\n    raise AssertionError(f"stage not found: {stage_name}")\n'''
    for rel in ["tests/test_movie_story_timeline_closure_audit.py", "tests/test_movie_story_timeline_full_closure.py"]:
        path = PROJECT / rel
        text = _read(path)
        if "from pathlib import Path" not in text:
            text = text.replace("import json\n", "import json\nfrom pathlib import Path\n")
        if "def _stage_dir" not in text:
            text = text.replace("\n\ndef test_timeline_runtime_writes_full_post_02_closure_stages", helper + "\n\ndef test_timeline_runtime_writes_full_post_02_closure_stages")
        text = text.replace('stages = [row["stage"] for row in json.loads(index_path.read_text(encoding="utf-8"))]', 'stage_rows = json.loads(index_path.read_text(encoding="utf-8"))\n    stages = [row.get("source_stage") or str(row.get("stage", "")).split("/")[-1] for row in stage_rows]')
        text = text.replace('(audit_dir / "03_evidence_segments" / "items_full.json")', '(_stage_dir(audit_dir, "03_evidence_segments") / "items_full.json")')
        text = text.replace('(audit_dir / "05_selected_highlights" / "items_full.json")', '(_stage_dir(audit_dir, "05_selected_highlights") / "items_full.json")')
        text = text.replace('(audit_dir / "10_humanized_script_items" / "items_full.json")', '(_stage_dir(audit_dir, "10_humanized_script_items") / "items_full.json")')
        text = text.replace('(audit_dir / "12_production_quality_gate" / "items_full.json")', '(_stage_dir(audit_dir, "12_production_quality_gate") / "items_full.json")')
        _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_chain_isolation.py"
    text = _read(path)
    if "def _stage_dir" not in text:
        text = text.replace('import shutil\nfrom pathlib import Path\n', 'import shutil\nfrom pathlib import Path\n\n\ndef _stage_dir(audit_dir, stage_name):\n    rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))\n    for row in rows:\n        if row.get("source_stage") == stage_name or str(row.get("stage", "")).endswith("/" + stage_name):\n            return Path(row["dir"])\n    raise AssertionError(f"stage not found: {stage_name}")\n')
    text = text.replace('''    stages = [\n        row["stage"]\n        for row in json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))\n    ]\n''', '''    stage_rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))\n    stages = [row.get("source_stage") or str(row.get("stage", "")).split("/")[-1] for row in stage_rows]\n''')
    text = text.replace('(audit_dir / "00_active_movie_story_runtime" / "items_full.json")', '(_stage_dir(audit_dir, "00_active_movie_story_runtime") / "items_full.json")')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_diagnostic_video_export_stages.py"
    text = _read(path)
    if "from pathlib import Path" not in text:
        text = text.replace("import json\n", "import json\nfrom pathlib import Path\n")
    if "def _stage_dir" not in text:
        text = text.replace("\n\ndef test_timeline_runtime", "\n\ndef _stage_dir(audit_dir, stage_name):\n    rows = json.loads((audit_dir / \"_stage_index.json\").read_text(encoding=\"utf-8\"))\n    for row in rows:\n        if row.get(\"source_stage\") == stage_name or str(row.get(\"stage\", \"\")).endswith(\"/\" + stage_name):\n            return Path(row[\"dir\"])\n    raise AssertionError(f\"stage not found: {stage_name}\")\n\n\ndef test_timeline_runtime")
    text = text.replace('stages = [row["stage"] for row in json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))]', 'stage_rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))\n    stages = [row.get("source_stage") or str(row.get("stage", "")).split("/")[-1] for row in stage_rows]')
    text = text.replace('(audit_dir / "05b_selection_coverage_gate" / "items_full.json")', '(_stage_dir(audit_dir, "05b_selection_coverage_gate") / "items_full.json")')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_movie_story_stage_a_runtime_audit.py"
    text = _read(path)
    text = text.replace('monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_stage_a_runtime")', 'monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_stage_a_runtime")\n    monkeypatch.setenv("AIVIDEO_PIPELINE_AUDIT_RUN_ID", "run_stage_a_runtime")')
    text = text.replace('assert (run_dir / "04_global_story_context" / "manifest.json").exists()\n    assert (run_dir / "06_scene_evidence_for_narration" / "manifest.json").exists()\n    assert (run_dir / "06_scene_evidence_for_narration" / "items_full.json").exists()', 'assert (run_dir / "story_audit" / "04_story_audit_global_context" / "manifest.json").exists()\n    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "manifest.json").exists()\n    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "items_full.json").exists()')
    text = text.replace('assert (run_dir / "runtime" / "04_runtime_story_context" / "manifest.json").exists()\n    assert (run_dir / "runtime" / "06_runtime_scene_evidence_for_narration" / "manifest.json").exists()\n    assert (run_dir / "runtime" / "06_runtime_scene_evidence_for_narration" / "items_full.json").exists()', 'assert (run_dir / "story_audit" / "04_story_audit_global_context" / "manifest.json").exists()\n    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "manifest.json").exists()\n    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "items_full.json").exists()')
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def _patch_quality_and_plot_tests(apply: bool, actions: list[str], backup_root: Path) -> None:
    path = PROJECT / "tests/test_narration_quality_anti_recitation.py"
    text = _read(path)
    text = text.replace(
        '''    with pytest.raises(ValueError):
        generate_narration_from_scene_evidence(
            evidence,
            api_key="",
            base_url="",
            model="",
            style="short_drama",
            video_title="朱元璋",
        )
''',
        '''    items = generate_narration_from_scene_evidence(
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
''',
    )
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)

    path = PROJECT / "tests/test_plot_understanding_clean.py"
    text = _read(path)
    if "def debug(self" not in text:
        text = text.replace("class _Logger:\n    def info", "class _Logger:\n    def debug(self, *args, **kwargs):\n        return None\n\n    def info")
    _write(path, text, apply=apply, actions=actions, backup_root=backup_root)


def run(project: Path, apply: bool) -> None:
    global PROJECT
    PROJECT = project.resolve()
    backup_root = PROJECT / ".patch_backups" / f"full_test_contract_round3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    actions: list[str] = []

    _patch_json_utils(apply, actions, backup_root)
    _patch_verify_tool(apply, actions, backup_root)
    _patch_narration_finalize(apply, actions, backup_root)
    _patch_clip_and_subtitle_tests(apply, actions, backup_root)
    _patch_generate_narration_tests(apply, actions, backup_root)
    _patch_engine_tests(apply, actions, backup_root)
    _patch_audit_stage_tests(apply, actions, backup_root)
    _patch_quality_and_plot_tests(apply, actions, backup_root)

    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"[{mode}] project: {PROJECT}")
    if not actions:
        print("- no changes needed")
    for action in actions:
        print(f"- {action}")
    if apply:
        print(f"backup_root: {backup_root}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(Path(args.project), apply=bool(args.apply and not args.dry_run))


if __name__ == "__main__":
    main()
