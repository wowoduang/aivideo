# -*- coding: utf-8 -*-
from __future__ import annotations

"""
patch_aivideo_cleanup_old_visual_evidence.py

自动清理 aivideo 中 AI 误留下的 movie_story selected-highlight 后置视觉证据链。

本补丁只做工程收敛：
- 不修改基础双轮链 / 视觉增强链的两轮提示词；
- 不扩大视觉能力；
- 不恢复 legacy/native 主流程；
- 不新增 fallback 或 compatibility wrapper；
- 删除 two_round_visual 与旧后置 selected-highlight 抽帧证据包之间的错误绑定。

用法：
    python patch_aivideo_cleanup_old_visual_evidence.py --project /path/to/aivideo --dry-run
    python patch_aivideo_cleanup_old_visual_evidence.py --project /path/to/aivideo --apply
"""

import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PatchAction:
    kind: str
    path: Path
    message: str


class ProjectPatcher:
    def __init__(self, *, project: Path, dry_run: bool) -> None:
        self.project = project.resolve()
        self.dry_run = dry_run
        self.actions: list[PatchAction] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_root = self.project / ".patch_backups" / f"cleanup_old_visual_evidence_{timestamp}"

    def run(self) -> None:
        self._assert_project_root()
        self._patch_local_job_runner()
        self._patch_api_schema()
        self._patch_frontend_api()
        self._patch_frontend_pages()
        self._patch_engine_guard_comments()
        self._patch_two_round_feature_modes_doc()
        self._patch_old_runtime_comments()
        self._archive_selected_highlight_workflow()
        self._patch_tests()
        self._patch_docs()
        self._print_summary()

    def _assert_project_root(self) -> None:
        required = [
            self.project / "app" / "services" / "local_job_runner.py",
            self.project / "app" / "api" / "schemas" / "jobs.py",
            self.project / "app" / "services" / "movie_story" / "two_round_feature_modes.py",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError("project root is invalid; missing: " + ", ".join(missing))

    def _rel(self, path: Path) -> Path:
        return path.relative_to(self.project)

    def _record(self, kind: str, path: Path, message: str) -> None:
        self.actions.append(PatchAction(kind=kind, path=self._rel(path), message=message))

    def _read(self, relative: str) -> str:
        path = self.project / relative
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")

    def _write(self, relative: str, content: str) -> None:
        path = self.project / relative
        if self.dry_run:
            self._record("modify", path, "preview content rewrite")
            return
        self._backup(path)
        path.write_text(content, encoding="utf-8", newline="\n")
        self._record("modify", path, "rewritten")

    def _backup(self, path: Path) -> None:
        if not path.exists():
            return
        backup_path = self.backup_root / path.relative_to(self.project)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)

    def _replace_required(self, text: str, old: str, new: str, *, label: str) -> str:
        if old not in text:
            raise RuntimeError(f"required replacement block not found: {label}")
        return text.replace(old, new, 1)

    def _remove_required_line(self, text: str, line: str, *, label: str) -> str:
        if line not in text:
            raise RuntimeError(f"required line not found: {label}")
        return text.replace(line, "", 1)

    def _patch_local_job_runner(self) -> None:
        relative = "app/services/local_job_runner.py"
        text = self._read(relative)
        start_marker = "            # OPTIONAL LEGACY REVIEW EVIDENCE POST-PROCESSOR:"
        end_marker = "            return result"
        start = text.find(start_marker)
        if start < 0:
            raise RuntimeError("legacy visual evidence post-processor block not found")
        end = text.find(end_marker, start)
        if end < 0:
            raise RuntimeError("return marker after legacy visual evidence block not found")
        replacement = (
            "            # two_round_visual 在第一轮多模态 prompt 前已经完成视觉证据准备。\n"
            "            # 第二轮产物直接进入剪辑/导出，不再运行 selected-highlight 后置抽帧复核链。\n"
        )
        text = text[:start] + replacement + text[end:]
        forbidden = [
            "movie_story_enable_visual_evidence",
            "selected_highlight_visual_evidence_workflow",
            "build_selected_highlight_visual_evidence_package",
        ]
        for token in forbidden:
            if token in text:
                raise RuntimeError(f"local_job_runner still contains forbidden legacy token: {token}")
        self._write(relative, text)

    def _patch_api_schema(self) -> None:
        relative = "app/api/schemas/jobs.py"
        text = self._read(relative)
        text = self._remove_required_line(
            text,
            "    movie_story_enable_visual_evidence: bool = False\n",
            label="remove schema legacy enable flag",
        )
        text = self._remove_required_line(
            text,
            "    movie_story_selected_highlight_max_frames: int = 6\n",
            label="remove schema legacy selected-highlight frame cap",
        )
        self._write(relative, text)

    def _patch_frontend_api(self) -> None:
        relative = "web/src/lib/api.ts"
        text = self._read(relative)
        text = self._remove_required_line(
            text,
            "  movie_story_enable_visual_evidence?: boolean;\n",
            label="remove frontend request type legacy visual flag",
        )
        text = self._remove_required_line(
            text,
            "        movie_story_enable_visual_evidence: Boolean(request.movie_story_enable_visual_evidence),\n",
            label="remove frontend request body legacy visual flag",
        )
        self._write(relative, text)

    def _patch_frontend_pages(self) -> None:
        for relative, label in [
            ("web/src/pages/editor/Analysis.tsx", "Analysis.tsx legacy visual flag"),
            ("web/src/pages/editor/Material.tsx", "Material.tsx legacy visual flag"),
        ]:
            text = self._read(relative)
            text = self._remove_required_line(
                text,
                "        movie_story_enable_visual_evidence: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy) === 'two_round_visual',\n"
                if "Analysis.tsx" in relative
                else "        movie_story_enable_visual_evidence: normalizeMovieStoryStrategy(config.movieStoryStrategy) === 'two_round_visual',\n",
                label=label,
            )
            self._write(relative, text)

    def _patch_engine_guard_comments(self) -> None:
        relative = "app/services/movie_story/engines.py"
        text = self._read(relative)
        text = self._replace_required(
            text,
            "    # Active movie_story must be rebuilt around candidate/highlight selection,\n"
            "    # selected_highlight_visual_evidence_workflow, and the two-round narration chain.\n"
            "    # The TikTok/Douyin-like long-video-to-multiple-shorts product should be\n"
            "    # implemented separately as multi_short_video_pipeline, not through old Native Runtime.\n",
            "    # Active movie_story must use explicit current mainflows: base two_round,\n"
            "    # two_round_visual first-round multimodal evidence, and the\n"
            "    # TikTok/Douyin-like multi_short_video_pipeline product path.\n"
            "    # Do not reconnect old Native Runtime as a hidden mainflow or fallback.\n",
            label="engine guard comment",
        )
        text = self._replace_required(
            text,
            "            \"movie_story_script old Native/Legacy mainflow is disabled; \"\n"
            "            \"connect the explicit candidate-selection -> selected_highlight_visual_evidence_workflow -> \"\n"
            "            \"two-round narration pipeline instead.\"\n"
            "        )\n",
            "            \"movie_story_script old Native/Legacy mainflow is disabled; \"\n"
            "            \"use the explicit base two_round / two_round_visual / \"\n"
            "            \"multi_short_video_pipeline flows instead.\"\n"
            "        )\n",
            label="engine guard error message",
        )
        self._write(relative, text)

    def _patch_two_round_feature_modes_doc(self) -> None:
        relative = "app/services/movie_story/two_round_feature_modes.py"
        text = self._read(relative)
        text = self._replace_required(
            text,
            "消费者：\n"
            "- app.services.local_job_runner 的 movie_story_script job\n"
            "- selected_highlight_visual_evidence_workflow\n"
            "- 前端 movie_story_script 结果预览\n",
            "消费者：\n"
            "- app.services.local_job_runner 的 movie_story_script job\n"
            "- 前端 movie_story_script 结果预览\n"
            "- 后续剪辑/导出链路\n",
            label="two_round_feature_modes consumer doc",
        )
        self._write(relative, text)

    def _patch_old_runtime_comments(self) -> None:
        replacements = [
            (
                "app/services/segment_visual_understanding.py",
                "        # Old Native Runtime visual-card enrichment is not part of the active\n"
                "        # movie_story mainflow. Selected-highlight visual facts are now prepared\n"
                "        # by app.services.movie_story.selected_highlight_visual_evidence_workflow.\n",
                "        # Old Native Runtime visual-card enrichment is not part of the active\n"
                "        # movie_story mainflow. Formal two_round_visual prepares first-round\n"
                "        # evidence in app.services.movie_story.two_round_visual_narration.\n",
                "segment_visual_understanding old workflow comment",
            ),
            (
                "app/services/movie_story/movie_story_native_engine.py",
                "            # Old Native Runtime per-highlight visual-card LLM enrichment is\n"
                "            # disabled in the active mainflow. Selected-highlight visual facts\n"
                "            # are prepared by selected_highlight_visual_evidence_workflow.\n",
                "            # Old Native Runtime per-highlight visual-card LLM enrichment is\n"
                "            # disabled in the active mainflow. Formal two_round_visual prepares\n"
                "            # first-round visual evidence before multimodal analysis.\n",
                "movie_story_native_engine old workflow comment",
            ),
        ]
        for relative, old, new, label in replacements:
            text = self._read(relative)
            text = self._replace_required(text, old, new, label=label)
            self._write(relative, text)

    def _archive_selected_highlight_workflow(self) -> None:
        moves = [
            (
                "app/services/movie_story/selected_highlight_visual_evidence_workflow.py",
                "deprecated/legacy_archive/movie_story/selected_highlight_visual_evidence_workflow.py",
            ),
            (
                "tests/movie_story/test_selected_highlight_visual_evidence_workflow.py",
                "deprecated/legacy_archive/tests/movie_story/selected_highlight_visual_evidence_workflow_test.py.archived",
            ),
            (
                "tests/movie_story/test_two_round_visual_input_packager.py",
                "deprecated/legacy_archive/tests/movie_story/two_round_visual_input_packager_legacy_api_test.py.archived",
            ),
            (
                "tests/movie_story/test_visual_focus_segments.py",
                "deprecated/legacy_archive/tests/movie_story/visual_focus_segments_legacy_api_test.py.archived",
            ),
        ]
        for src_relative, dst_relative in moves:
            src = self.project / src_relative
            dst = self.project / dst_relative
            if not src.exists():
                raise FileNotFoundError(src)
            if dst.exists():
                raise FileExistsError(dst)
            if self.dry_run:
                self._record("move", src, f"would move to {dst_relative}")
                continue
            self._backup(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            self._record("move", src, f"moved to {dst_relative}")

        readme = self.project / "deprecated" / "legacy_archive" / "movie_story" / "README.md"
        readme_content = (
            "# movie_story legacy archive\n\n"
            "本目录保存已经移出正式主流程的历史代码。\n\n"
            "## selected_highlight_visual_evidence_workflow.py\n\n"
            "该 workflow 是 AI 曾经误实现的 selected-highlight 后置视觉证据链：\n"
            "先生成 script/highlights，再对 selected highlights 抽帧、生成复核证据包。\n\n"
            "当前正式 `two_round_visual` 定义是：第一轮多模态 prompt 前完成本地视觉证据准备，\n"
            "第一轮多模态理解，第二轮文本写作，第二轮后直接进入剪辑/导出。\n\n"
            "本轮没有迁移该 workflow 中的代码，因为它围绕后置复核设计，\n"
            "不服务第一轮前的成本受控视觉证据准备。若未来需要 contact sheet 或路径命名能力，\n"
            "应重新按正式模块边界抽取，不得从主流程直接 import 本归档文件。\n\n"
            "同目录下的 *.py.archived 是旧 API 测试源，仅用于人工考古；\n"
            "它们不应被 pytest 收集，也不得通过补 compatibility wrapper 恢复。\n"
        )
        if self.dry_run:
            self._record("create", readme, "would write legacy archive README")
        else:
            readme.parent.mkdir(parents=True, exist_ok=True)
            if readme.exists():
                self._backup(readme)
            readme.write_text(readme_content, encoding="utf-8", newline="\n")
            self._record("create", readme, "wrote legacy archive README")

    def _patch_tests(self) -> None:
        relative = "tests/movie_story/test_movie_story_old_engine_dispatch_guard.py"
        text = self._read(relative)
        text = self._replace_required(
            text,
            "    assert \"selected_highlight_visual_evidence_workflow\" in source\n",
            "    assert \"selected_highlight_visual_evidence_workflow\" not in source\n",
            label="old engine guard selected workflow assertion",
        )
        self._write(relative, text)

        relative_new = "tests/movie_story/test_movie_story_no_legacy_visual_postprocessor.py"
        path_new = self.project / relative_new
        if path_new.exists():
            raise FileExistsError(path_new)
        content = (
            "# -*- coding: utf-8 -*-\n"
            "from __future__ import annotations\n\n"
            "\"\"\"Guards against reconnecting the old selected-highlight visual post-processor.\"\"\"\n\n"
            "from pathlib import Path\n\n\n"
            "def test_local_job_runner_does_not_trigger_legacy_visual_evidence_postprocessor() -> None:\n"
            "    source = Path(\"app/services/local_job_runner.py\").read_text(encoding=\"utf-8\")\n\n"
            "    assert \"movie_story_enable_visual_evidence\" not in source\n"
            "    assert \"selected_highlight_visual_evidence_workflow\" not in source\n"
            "    assert \"build_selected_highlight_visual_evidence_package\" not in source\n\n\n"
            "def test_frontend_and_schema_do_not_expose_legacy_visual_evidence_switch() -> None:\n"
            "    checked_paths = [\n"
            "        Path(\"app/api/schemas/jobs.py\"),\n"
            "        Path(\"web/src/lib/api.ts\"),\n"
            "        Path(\"web/src/pages/editor/Analysis.tsx\"),\n"
            "        Path(\"web/src/pages/editor/Material.tsx\"),\n"
            "    ]\n\n"
            "    for path in checked_paths:\n"
            "        source = path.read_text(encoding=\"utf-8\")\n"
            "        assert \"movie_story_enable_visual_evidence\" not in source\n"
            "        assert \"movie_story_selected_highlight_max_frames\" not in source\n"
        )
        if self.dry_run:
            self._record("create", path_new, "would create guard test")
        else:
            path_new.parent.mkdir(parents=True, exist_ok=True)
            path_new.write_text(content, encoding="utf-8", newline="\n")
            self._record("create", path_new, "created guard test")

    def _patch_docs(self) -> None:
        self._patch_status_doc()
        self._patch_pending_doc()
        self._patch_adr_doc()

    def _patch_status_doc(self) -> None:
        relative = "docs/status/two_round_visual_status.md"
        text = self._read(relative)
        text = self._replace_required(
            text,
            "**最后更新**：2026-05-22  \n"
            "**状态**：第一轮多模态骨架已接通，等待真实视频/视觉模型联调\n",
            "**最后更新**：2026-05-25  \n"
            "**状态**：视觉增强链已达到及格测试状态；本轮完成旧后置 selected-highlight 视觉证据链主流程清理\n",
            label="status header",
        )
        text = self._replace_required(
            text,
            "4. visual_frame_sampler.py 增加全片低密度帧和 visual_focus_segments 详细帧接口。\n"
            "5. two_round_feature_modes.py 接通 visual_enabled=True 到真实 two_round_visual 路由。\n"
            "6. local_job_runner.py 不再把 two_round_visual 等同于后置 selected_highlight 证据包。\n"
            "7. API schema 和前端说明同步为第一轮多模态增强。\n"
            "8. 新增/更新 tests，覆盖 visual 模式不调用 text-only fake chain。\n",
            "4. visual_timeline_sampler.py 提供全片低密度帧和 visual_focus_segments 详细帧接口。\n"
            "5. two_round_feature_modes.py 接通 visual_enabled=True 到真实 two_round_visual 路由。\n"
            "6. local_job_runner.py 删除旧 selected-highlight 后置视觉证据处理器。\n"
            "7. API schema 和前端删除 movie_story_enable_visual_evidence 旧开关。\n"
            "8. selected_highlight_visual_evidence_workflow 已移入 deprecated/legacy_archive，不再属于正式主流程。\n"
            "9. 新增/更新 tests，覆盖 visual 模式不调用 text-only fake chain，并防止旧后置抽帧链回流。\n",
            label="status completed implementation list",
        )
        text = self._replace_required(
            text,
            "4. 检查第二轮输出与剪辑合成模块的最终片段契约。\n"
            "5. 旧 selected_highlight_visual_evidence_workflow 仍需后续清理定位。\n",
            "4. 检查第二轮输出与剪辑合成模块的最终片段契约。\n"
            "5. 长视频拆多个短视频流程继续作为正式产品主流程收敛，避免借旧 native/legacy 主流程实现。\n",
            label="status unfinished list",
        )
        text = self._replace_required(
            text,
            "3. 把旧 selected_highlight_visual_evidence_workflow 当成 two_round_visual 主流程。\n",
            "3. 把 deprecated/legacy_archive 中的旧 selected_highlight_visual_evidence_workflow 重新接回主流程。\n",
            label="status risk list",
        )
        self._write(relative, text)

    def _patch_pending_doc(self) -> None:
        relative = "PENDING.md"
        text = self._read(relative)
        pending_block = (
            "\n### [PEND-202] 清理 selected_highlight_visual_evidence_workflow 的定位\n\n"
            "**状态**：待分析\n\n"
            "**背景**：\n\n"
            "旧链路中存在后置 selected highlight 视觉证据包。该模块不应再被当作 `two_round_visual` 主流程。\n\n"
            "**目标**：\n\n"
            "明确它是后置复核/历史遗留能力，或迁移其中可复用的抽帧工具能力。\n"
        )
        if pending_block not in text:
            raise RuntimeError("PEND-202 block not found in PENDING.md")
        text = text.replace(pending_block, "\n", 1)
        done_insert = (
            "\n### [DONE-004] 清理 selected-highlight 后置视觉证据链\n\n"
            "**完成日期**：2026-05-25\n\n"
            "**方案**：\n\n"
            "- 删除正式主流程中的 `movie_story_enable_visual_evidence` 旧开关。\n"
            "- 删除 `local_job_runner.py` 对 selected-highlight 后置抽帧复核 workflow 的调用。\n"
            "- 将 `selected_highlight_visual_evidence_workflow.py` 和对应旧测试移入 `deprecated/legacy_archive/`。\n"
            "- 未迁移该 workflow 内部代码：它围绕第二轮后 selected highlights 复核设计，\n"
            "  不服务当前正式 two_round_visual 的第一轮前成本受控视觉证据准备。\n"
            "- 归档旧 API 测试，防止它们要求恢复已废弃的 compatibility wrapper。\n"
            "- 新增 guard 测试，防止旧开关或旧 workflow 再次被接回正式主流程。\n\n"
        )
        marker = "\n\n## [PEND-STAGE2-VISUAL-TIMELINE]"
        if marker not in text:
            raise RuntimeError("PENDING done insertion marker not found")
        text = text.replace(marker, done_insert + marker, 1)
        self._write(relative, text)

    def _patch_adr_doc(self) -> None:
        relative = "docs/decisions/ADR-005-two-round-visual-first-round-multimodal.md"
        text = self._read(relative)
        insert_after = (
            "拒绝旧定义：\n\n"
            "```text\n"
            "text-only two_round 先生成文案\n"
            "  → 再对 selected highlights 抽帧\n"
            "  → 作为 two_round_visual\n"
            "```\n\n"
            "原因：这不能解决第一轮理解时的说话主体/对象误判。\n"
        )
        addition = (
            insert_after
            + "\n2026-05-25 清理状态：`selected_highlight_visual_evidence_workflow.py` 已移入 "
            "`deprecated/legacy_archive/`，`movie_story_enable_visual_evidence` 旧开关已从正式 "
            "API schema、前端请求和 `local_job_runner.py` 主流程删除。该 workflow 内部代码不迁移，"
            "因为它服务第二轮后复核，不服务第一轮前视觉证据准备。\n"
        )
        text = self._replace_required(text, insert_after, addition, label="ADR cleanup status insertion")
        self._write(relative, text)

    def _print_summary(self) -> None:
        mode = "DRY-RUN" if self.dry_run else "APPLIED"
        print(f"[{mode}] project: {self.project}")
        for action in self.actions:
            print(f"- {action.kind}: {action.path} | {action.message}")
        if not self.dry_run:
            print(f"backup_root: {self.backup_root}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean old selected-highlight visual evidence chain from aivideo.")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="aivideo project root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="preview changes only")
    mode.add_argument("--apply", action="store_true", help="apply changes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    patcher = ProjectPatcher(project=args.project, dry_run=bool(args.dry_run))
    patcher.run()


if __name__ == "__main__":
    main()
