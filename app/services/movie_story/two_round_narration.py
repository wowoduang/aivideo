from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from app.utils import workspace

ANALYSIS_PROMPT_TEMPLATE = '以下是一集电视剧的SRT字幕，我需要你做结构分析，不要输出正式文案正文。\n\n影视名称：[填入片名]\n本集信息：[第几集，主要剧情关键词]\n史观视角：[如阶层结构、失败者史观、权力结构]\n\n步骤一，建立剧情底图。\n\n用你对这部剧的已有认知，列出本集主要角色、人物关系、本集核心事件。不确定的标注"存疑"，不要强行填写。\n\n步骤二，划分故事段落。\n\n读完全部字幕后，按你对故事完结的判断，把本集划分成若干个故事段落。每段标注起止时间和这段戏的核心功能，一句话说明。\n\n步骤三，对每个故事段写理解。\n\n重要：步骤三严格在步骤二划定的每个故事段时间范围内分析，每个关键小戏的时间范围不得超出该故事段的起止时间。\n\n对步骤二划分出的每个故事段，逐一输出以下五项内容：\n\n故事段编号和标题：给这段戏起一个能概括其戏剧功能的名字，并在标题后标注本故事段的起止时间，格式为（MM:SS到MM:SS），作为本段所有关键小戏时间范围的边界约束。\n\n场景证据：用自己的语言描述这个故事段的完整戏剧过程，包括由什么触发、中间经历了什么、以什么收尾，人物的行动和情绪变化都要写进去。不抄台词，不少于100字。\n\n关键小戏：在本故事段的起止时间范围内，按时间顺序找出2到4个最有表达力的小戏。对每个关键小戏输出以下三项：\n\n    这场小戏发生了什么：用自己的语言描述这个时刻的戏剧内容，包括谁在场、发生了什么冲突或转变、情绪如何变化。不抄台词，不少于3句。\n\n    这场小戏的完整片段时间：从这场小戏情绪自然开始的那一刻，到情绪自然收尾的那一刻，给出起止时间，格式为MM:SS到MM:SS。这不是这句台词的开始和结束，而是这场小戏作为一个完整情绪单元的开始和结束。\n\n    强制验证（必须执行，不可跳过，逐项写出验证结果）：\n        范围检查：上方给出的时间范围是否在本故事段起止时间之内？如果超出，立即重新划定，直到在范围内为止。写出结果，格式为"在段内"或"已超出，已重划为MM:SS到MM:SS"。\n        秒数检查：计算时间范围的秒数。写出结果，格式为"共X秒"。\n        下限检查：如果不足60秒，必须重新向前或向后扩展边界，直到满足60秒为止。不允许跳过，不允许留到第二轮再扩展。写出结果，格式为"满足60秒下限"或"不满足，已扩展至MM:SS到MM:SS，共X秒"。\n\n深层理解：基于这个故事段，写3到6句有层次的洞察。第一句说这段戏在史观视角下揭示了什么；第二句说为什么会这样，背后的结构性原因是什么；第三句说这个理解可以怎样延伸或推进。写完之后这几句话应该能直接作为第二轮文案的素材，不需要再回头查字幕。\n\n情绪弧度：这个故事段从什么情绪开始，经历了什么变化，以什么情绪结束，一句话。\n\n步骤四，提出主线候选。\n\n基于步骤三对所有故事段的理解，在所选史观视角下，提出2到3条可能的文案主线。\n\n每条主线输出两项：主论点（一段话，整篇文案要说服观众相信的核心判断）；分论点序列（各一段话，3到6个递进分论点，逻辑是"不仅如此，更进一步"，不能是并列，每个分论点注明对应哪个故事段编号和哪个关键小戏）。\n\n步骤五，自动推荐主线。\n\n不要等待用户选择。从步骤四的候选里自动推荐1到2条最适合短视频成片的主线，素材复杂时允许第3条作为辅助线，并说明每条的推荐理由。\n\n输出要求：只输出结构分析，不输出正式文案。不要按字幕顺序逐段总结。不要把对白改写成旁白。不要出现"收到指令""我将遵循"之类自我声明。\n\n字幕内容如下：\n{raw_srt_text}\n'

WRITER_PROMPT_TEMPLATE = '以下是第一轮结构分析结果：\n{analysis_result}\n\n请从推荐主线中自动选择1条最有解释力、最适合成片的主线写文案。字幕原文不会出现在这里，你只能基于第一轮每个故事段的场景证据、深层理解和关键小戏来写，不要回头找台词。\n\n写文案前先做两件事。\n\n第一，把选定主线的主论点拆成3到6个分论点，每个分论点是主论点的一个递进维度，逻辑是"不仅如此，更进一步"，不是并列。把分论点序列列出来，标注每个分论点对应第一轮哪个故事段编号和哪个关键小戏，再开始写正文。\n\n第二，在开场和收尾中任选一个写，另一个不输出。开场和收尾都是对主论点的直接表达，不是对某个具体场景的解读。选好后，从整集字幕范围内找出2到4个按时间顺序排列的可拼接片段，每个片段给出起止时间，说明为什么这段画面能承载主论点。\n\n文案结构如下。\n\n开场（若选择写开场）：主论点最锋利的变体，直接成立，不铺垫。时间码为2到4个按时间顺序排列的可拼接片段。\n\n分论点一到六，根据主论点灵活决定数量，每个分论点写一段：基于对应故事段的场景证据和深层理解展开，有细节，有质地，不是概括句。不写"他说、她说、随后、接着"这种剧情流水账。不逐句复述，不把对白改写成旁白。\n\n收尾（若选择写收尾）：主论点的升维表达，角度偏转，不重复开场。用反问或留白，不做总结式升华。时间码为2到4个按时间顺序排列的可拼接片段。\n\n时间码规则。\n\n开场或收尾的时间码：从整集范围内提取2到4个最能承载主论点的片段，按时间顺序排列，每个片段格式为MM:SS到MM:SS，并注明这段画面为什么能代表主论点。\n\n分论点的时间码：直接继承第一轮对应关键小戏经过强制验证后的完整片段时间，不重新缩短。写完每段正文后，数这段文案的字数除以5得到最短所需画面秒数，检验继承的时间是否满足。如果不满足，向前或向后扩展，并在括号里注明：本段N字，朗读约需M秒，继承片段Q秒，是否扩展。\n\n分论点时间码尽量按原片时间递增；如果递进逻辑和原片时间冲突，优先保证主线表达。\n\n不要输出"收到指令""我将遵循"等自我声明。\n\n正式文案格式（开场版）：\n\n**开场**\n片段一 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n片段二 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n片段三 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n文案正文。\n\n**分论点一**\n[MM:SS ~ MM:SS]（本段N字，朗读约需M秒，继承片段Q秒，无需扩展/已扩展至XX秒）\n文案正文。\n\n**分论点二**\n[MM:SS ~ MM:SS]（本段N字，朗读约需M秒，继承片段Q秒，无需扩展/已扩展至XX秒）\n文案正文。\n\n如果主论点支撑，继续输出分论点三到六，格式相同。\n\n正式文案格式（收尾版）：\n\n**分论点一**\n[MM:SS ~ MM:SS]（本段N字，朗读约需M秒，继承片段Q秒，无需扩展/已扩展至XX秒）\n文案正文。\n\n**分论点二**\n[MM:SS ~ MM:SS]（本段N字，朗读约需M秒，继承片段Q秒，无需扩展/已扩展至XX秒）\n文案正文。\n\n如果主论点支撑，继续输出分论点三到六，格式相同。\n\n**收尾**\n片段一 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n片段二 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n片段三 [MM:SS ~ MM:SS]（说明为什么能代表主论点）\n文案正文。\n'

RAW_SRT_MARKERS = (
    "【原版 SRT 字幕】",
    "【原始 SRT 字幕】",
    "【原始SRT文本】",
    "【带时间戳的原版字幕】",
    "字幕内容如下：",
)

def debug_dir() -> Path:
    """返回双轮链调试目录。

    调试输出属于运行产物，统一写入外部 workspace/temp，避免在项目根目录
    重建 storage/temp。
    """
    return Path(workspace.temp_dir("raw_srt_debug", create=True))


def write_debug(name: str, text: Any) -> None:
    try:
        (debug_dir() / name).write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass  # 清理操作，忽略异常


def response_to_text(response: Any) -> str:
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
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def build_analysis_prompt(raw_srt_text: str) -> str:
    return ANALYSIS_PROMPT_TEMPLATE.format(
        title=env_text("MOVIE_STORY_TITLE", "未知剧名"),
        episode_info=env_text("MOVIE_STORY_EPISODE_INFO", "本集剧情由字幕判断"),
        history_view=env_text("MOVIE_STORY_HISTORY_VIEW", "阶层结构、失败者史观、权力结构"),
        raw_srt_text=raw_srt_text,
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


def build_writer_prompt(analysis_result: str) -> str:
    selected_mainline = env_text(
        "MOVIE_STORY_SELECTED_MAINLINE",
        "请从分析结果中的主线候选里，自动选择1到3条最有解释力、最适合成片的主线；默认优先1到2条，素材复杂时允许第3条作为辅助线。",
    )
    return WRITER_PROMPT_TEMPLATE.format(
        analysis_result=sanitize_analysis_result(analysis_result),
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
) -> str:
    if os.getenv("MOVIE_STORY_TWO_ROUND_DISABLE", "").lower() in {"1", "true", "yes", "on"}:
        return response_to_text(call_llm(full_prompt))

    raw_srt_text = extract_raw_srt(full_prompt)
    write_debug("last_original_single_prompt.txt", full_prompt)

    analysis_prompt = build_analysis_prompt(raw_srt_text)
    write_debug("last_analysis_prompt.txt", analysis_prompt)
    analysis_text = response_to_text(call_llm(analysis_prompt))
    write_debug("last_analysis_response.txt", analysis_text)

    writer_prompt = build_writer_prompt(analysis_text)
    write_debug("last_writer_prompt.txt", writer_prompt)
    writer_text = response_to_text(call_llm(writer_prompt))
    write_debug("last_writer_response.txt", writer_text)

    final_script = extract_formal_script(writer_text)
    write_debug("last_two_round_final_script.txt", final_script)
    return final_script
