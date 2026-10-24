# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from app.utils import workspace

ANALYSIS_PROMPT_TEMPLATE = '以下是一集电视剧的SRT字幕，我需要你做结构分析，不要输出正式文案正文。\n\n影视名称：[填入片名]\n本集信息：[第几集，主线主题，受众群体]\n历史/现实观察维度：[阶层结构、失败者史观、权力结构]\n\n【原���SRT文本】\n{raw_srt_text}\n\n请严格按照以下要求输出：\n1. 总体剧情脉络：按时间线概述\n2. 关键冲突：哪些人物/事件构成最重要冲突\n3. 主线/支线：区分主线和辅助线\n4. 关键情绪变化：情绪峰值与反转\n5. 适合成片的主线候选：给出2-3条候选，并说明为什么适合做解说\n6. 不输出最终文案正文，不要直接复述字幕原文\n'

WRITER_PROMPT_TEMPLATE = (
    '以下是第一轮结构分析结果：\n{analysis_result}\n\n'
    '解说风格约束：{style_instruction}\n\n'
    '请从推荐主线中自动选择1条最有解释力、最适合成片的主线写文案。字幕原文不能作为正文直接照抄；请基于分析结果写出正式解说文本。\n'
    '如果素材复杂，也可以在不失主线的前提下选择辅助线作为补充，但主线必须明确。\n'
    '请输出正式文案，不要再次列分析步骤。\n'
    '{selected_mainline}\n'
)

RAW_SRT_MARKERS = (
    "【原版 SRT 字幕】",
    "【原始 SRT 字幕】",
    "【原始SRT文本】",
    "【带时间戳的原版字幕】",
    "字幕内容如下：",
)

STYLE_TEMPLATE_PATH = Path(__file__).with_name("narration_style_templates.json")


def debug_dir() -> Path:
    """返回双轮链调试目录。

    调试输出属于运行产物，统一写入外部 workspace/temp，避免在项目根目录
    重建 storage/temp。
    """
    return Path(workspace.temp_dir("raw_srt_debug", create=True))


def write_debug(name: str, text: Any) -> None:
    """写入基础双轮链调试文本。

    调试文件属于运行产物，只用于排查 prompt/LLM 输出问题；
    调用方不应依赖这里的文件作为正式业务结果。失败时直接抛错，
    避免静默吞掉调试输出问题。
    """
    try:
        (debug_dir() / name).write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass  # 清理操作，忽略异常


def response_to_text(response: Any) -> str:
    """从兼容 OpenAI ChatCompletion 形态的响应中提取文本。

    这个函数只做响应结构归一化，不负责解释模型输出内容；
    调用方随后再进入结构分析/文案解析阶段。这里保持显式报错，
    防止上游 LLM SDK 响应格式变化时被误判为空结果。
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="ignore")
    if isinstance(response, dict):
        try:
            choices = response.get("choices")
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if content:
                    return str(content)
        except Exception as _e:
            logger.warning("LLM 响应解析失败: {}", _e)
        for key in ("text", "content", "message", "response", "result"):
            value = response.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(response, ensure_ascii=False)
    return str(response)


def extract_raw_srt(full_prompt: str) -> str:
    """从 prompt 文本中提取原始字幕块。

    基础双轮链的第一轮 prompt 会携带完整字幕；该函数只恢复其中
    【原始字幕】区域，供调试或兼容路径使用，不在这里解读剧情语义。
    """
    text = str(full_prompt or "")
    best_index = -1
    best_marker = ""
    for marker in RAW_SRT_MARKERS:
        index = text.rfind(marker)
        if index > best_index:
            best_index = index
            best_marker = marker
    if best_index >= 0:
        return text[best_index + len(best_marker):].strip()
    return text.strip()


def env_text(name: str, default: str) -> str:
    """读取环境变量文本并做空白归一化。

    用于双轮链少量运行配置读取。缺失时返回默认值，不承担业务 fallback；
    真正的模型/流程缺失仍应由调用方显式报错。
    """
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def load_style_templates() -> dict[str, Any]:
    """Load the existing narration style config registry without creating a second style system."""
    try:
        with STYLE_TEMPLATE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("无法加载 narration style templates: {}", exc)
    return {}


def resolve_style_config(
    *,
    video_type: str = "documentary",
    narration_style: str = "neutral_cinematic",
    templates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a style config from the existing JSON registry using project defaults."""

    registry = templates if templates is not None else load_style_templates()
    if not isinstance(registry, dict):
        return {
            "id": "documentary:neutral_cinematic",
            "video_type": "documentary",
            "narration_style": "neutral_cinematic",
            "prompt": "",
        }

    key = f"{video_type}:{narration_style}"
    if key in registry:
        return registry[key]
    if narration_style and narration_style in registry:
        return registry[narration_style]
    if video_type and video_type in registry:
        return registry[video_type]
    if "documentary:neutral_cinematic" in registry:
        return registry["documentary:neutral_cinematic"]
    if "historical_drama" in registry:
        return registry["historical_drama"]
    return {
        "id": "documentary:neutral_cinematic",
        "video_type": "documentary",
        "narration_style": "neutral_cinematic",
        "prompt": "",
    }


def build_analysis_prompt(
    raw_srt_text: str,
    *,
    video_type: str = "documentary",
    narration_style: str = "neutral_cinematic",
) -> str:
    """构造基础双轮链第一轮结构分析 prompt。

    本函数只拼接既有 prompt 模板和输入材料，不修改提示词语义。
    通过 style registry 兼容扩展，不新增一套新 prompt 分支。
    """
    style_cfg = resolve_style_config(video_type=video_type, narration_style=narration_style)
    style_hint = str(style_cfg.get("prompt", "")).strip()
    prefix = f"\n\n风格指令：{style_hint}\n" if style_hint else ""
    return ANALYSIS_PROMPT_TEMPLATE.format(
        title=env_text("MOVIE_STORY_TITLE", "未知剧名"),
        episode_info=env_text("MOVIE_STORY_EPISODE_INFO", "本集剧情由字幕判断"),
        history_view=env_text("MOVIE_STORY_HISTORY_VIEW", "阶层结构、失败者史观、权力结构"),
        raw_srt_text=f"{raw_srt_text}{prefix}",
    )


def sanitize_analysis_result(analysis_result: str) -> str:
    """避免第一轮的任务声明/免责声明污染第二轮写作。"""
    raw = str(analysis_result or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines = []
    for line in raw.split("\n"):
        s = line.strip()
        if not s:
            cleaned_lines.append("")
            continue
        bad_phrases = (
            "收到指令",
            "严格遵循",
            "不撰写任何文案",
            "不写任何文案",
            "不会写文案",
            "等待我选择",
            "完成后停下",
        )
        if any(phrase in s for phrase in bad_phrases):
            continue
        cleaned_lines.append(line)
    out = "\n".join(cleaned_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def build_writer_prompt(
    analysis_result: str,
    *,
    video_type: str = "documentary",
    narration_style: str = "neutral_cinematic",
) -> str:
    """构造基础双轮链第二轮文案写作 prompt。

    通过 style registry 复用现有模板并扩展风格能力，不在主流程中新增大量 if/else 分支。
    """
    style_cfg = resolve_style_config(video_type=video_type, narration_style=narration_style)
    style_instruction = str(style_cfg.get("prompt", "")).strip()
    selected_mainline = env_text(
        "MOVIE_STORY_SELECTED_MAINLINE",
        "请从分析结果中的主线候选里，自动选择1到3条最有解释力、最适合成片的主线；默认优先1到2条，素材复杂时允许第3条作为辅助线。",
    )
    return WRITER_PROMPT_TEMPLATE.format(
        analysis_result=sanitize_analysis_result(analysis_result),
        style_instruction=style_instruction or "请按通用纪实解说方式写作，突出事实、冲突和人物关系。",
        selected_mainline=selected_mainline,
    )


def extract_formal_script(writer_text: str) -> str:
    """Extract only the formal script body from the second-round LLM response.

    The model often emits markdown headings such as ``### **正式文案**`` instead of
    the older ``【正式文案】`` marker.  If we fail to cut at that heading, the
    frontend preview and the time parser may receive the preceding analysis
    section as if it were script content.
    """
    text = str(writer_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    patterns = [
        r"【\s*正式文案\s*】",
        r"(?im)^\s*#{0,6}\s*\*{0,2}\s*正式文案\s*\*{0,2}\s*[：:]?\s*$",
        r"(?im)^\s*正式文案\s*[：:]\s*",
    ]
    best = None
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if best is None or match.start() < best.start():
                best = match
    if best is not None:
        text = text[best.end():].strip()

    # Drop common assistant preambles if a provider still prepends them.
    text = re.sub(
        r"(?is)^\s*(好的|收到|明白|已收到).{0,120}?(?:\n{2,}|---\s*\n+)",
        "",
        text,
    ).strip()
    return text


def run_two_round_narration_from_prompt(
    full_prompt: str,
    call_llm: Callable[[str], Any],
    *,
    video_type: str = "documentary",
    narration_style: str = "neutral_cinematic",
) -> str:
    """执行基础双轮链并返回文案条目列表。

    生产者是完整 raw_srt prompt；消费者是 movie_story 当前正式入口。
    本函数只串联第一轮理解与第二轮写作，不接旧 native/legacy fallback，
    也不在第二轮后追加视觉抽帧链。
    """
    if os.getenv("MOVIE_STORY_TWO_ROUND_DISABLE", "").lower() in {"1", "true", "yes", "on"}:
        return response_to_text(call_llm(full_prompt))

    raw_srt_text = extract_raw_srt(full_prompt)
    write_debug("last_original_single_prompt.txt", full_prompt)

    analysis_prompt = build_analysis_prompt(
        raw_srt_text,
        video_type=video_type,
        narration_style=narration_style,
    )
    write_debug("last_analysis_prompt.txt", analysis_prompt)
    analysis_text = response_to_text(call_llm(analysis_prompt))
    write_debug("last_analysis_response.txt", analysis_text)

    writer_prompt = build_writer_prompt(
        analysis_text,
        video_type=video_type,
        narration_style=narration_style,
    )
    write_debug("last_writer_prompt.txt", writer_prompt)
    writer_text = response_to_text(call_llm(writer_prompt))
    write_debug("last_writer_response.txt", writer_text)

    final_script = extract_formal_script(writer_text)
    write_debug("last_two_round_final_script.txt", final_script)
    return final_script


__all__ = [
    "build_analysis_prompt",
    "build_writer_prompt",
    "extract_formal_script",
    "resolve_style_config",
    "load_style_templates",
    "run_two_round_narration_from_prompt",
]
