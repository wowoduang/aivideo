#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class NarrationGenerationPrompt(ParameterizedPrompt):
    """影视解说文案生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="narration_generation",
            category="movie_story_narration",
            version="v1.2",
            description="基于剧情证据、影片上下文与风格样本生成单段影视解说文案",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["电影", "影视解说", "文案生成", "风格样本"],
            parameters=[
                "segment_json",
                "global_summary_json",
                "project_context_json",
                "style_guide",
                "style_examples",
                "char_budget",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=[
                "segment_json",
                "global_summary_json",
                "project_context_json",
                "style_guide",
                "style_examples",
                "char_budget",
            ],
        )
        self._system_prompt = (
            "你是中文影视解说文案助手。"
            "你要根据剧情证据、影片题材提示和解说风格，写出适合口播的单段解说。"
            "必须让解说贴合当前时间窗画面；允许概括，但不能把前后片段或全片总结写进当前片段。"
        )

    def get_template(self) -> str:
        return """# 任务
你需要根据“已校核剧情片段”和“项目上下文”生成一段适合口播的影视解说。

# 关键原则
1. 不得编造未被剧情理解层确认的信息。
2. 允许对片段做概括总结，不要求逐句复述字幕；只要主线事实、人物关系、因果方向不说反即可。
3. 如果你熟悉 `${project_context_json}` 中这部影片，可以利用对影片本身的既有知识帮助辨认角色、身份和场面，但必须严格受当前时间窗限制，不能提前写到后续情节。
4. 如果 `is_opening_segment=true`，第一句必须先交代开场局势、人物或场面，不能整段零开场。
5. 只有 `speaker_attribution_confidence=single_explicit` 时，才可以写成“某人说/某人命令”；否则要用“有人/对方/现场/这番话”等中性说法，避免乱认说话人。
6. `plot_function` 为“铺垫/节奏缓冲”的段落简短，`plot_function` 为“反转/情感爆发/信息揭露”的段落可以重点展开。
7. 输出长度要服从 `char_budget`，因为它直接决定配音时长和视频匹配节奏。
8. 原声保留只适用于短促、情绪强、现场感强的片段；长段默认仍以解说为主。
9. 风格优先参考样本文案，而不是自己发明口吻。
10. `segment_json` / `project_context_json` 中如果给了 `timestamp`、`start/end`、`visual_summary`、`representative_frames`，它们就是当前要合成的片段画面证据。
11. 解说必须严格贴合当前片段：只写当前时间窗内字幕和代表帧能支持的内容；可以有 2-3 秒画面误差，但不能提前讲下一段、不能回讲上一段、不能写全局总结。
12. 全局剧情摘要只用于理解人物关系和背景，不得作为当前片段画面的直接解说材料。
13. 如果当前片段证据不足，就写保守过渡句；宁可少讲，不要讲错画面。
14. 如果 `visual_evidence_pack`、`segment_visual_card` 或 `current_clip_visual_evidence` 存在，第一优先从可见动作、人物姿态、表情、物件、场景开口写；字幕负责事实，画面负责质感。
15. 不要写内部分析腔，禁止使用“这一段主要交代”“这一段承担的是”“信息揭露功能”“推动矛盾升级”“重点不在台词本身”“悬念加重”等表达。
16. 不要复述台词。要把台词背后的处境、压力、动作后果讲出来，语言像真人短视频解说。
17. 只输出 JSON，不要额外解释。

# 输出 JSON 结构
{
  "narration": "最终口播文案，首段要有开场感",
  "raw_voice_keep": false,
  "tone": "一句话概括语气",
  "opening_type": "悬念 / 直叙 / 情绪推进 / 过渡",
  "risk_note": "如果证据不足，这里说明为何保守表达"
}

# 项目上下文
${project_context_json}

# 全局剧情摘要
${global_summary_json}

# 当前剧情片段
${segment_json}

# 风格说明
如果这里出现“历史正剧深度解说｜通用AI提示词模板”，它就是本轮直接喂给 AI 的写作模板，必须按模板执行；同时仍要遵守当前 segment_json 的时间轴、证据边界和 JSON 输出结构。
${style_guide}

# 风格样本
${style_examples}

# 字数上限
${char_budget}
"""


class FullSubtitleTimelineNarrationPrompt(ParameterizedPrompt):
    """整段字幕时间轴优先的影视解说文案生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="full_subtitle_timeline_narration",
            category="movie_story_narration",
            version="v1.0",
            description="先根据完整字幕/高光时间轴生成连续解说稿，再回填到对应片段",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["电影", "影视解说", "整段文案", "字幕时间轴", "风格样本"],
            parameters=[
                "timeline_json",
                "source_timeline_json",
                "global_summary_json",
                "project_context_json",
                "style_guide",
                "style_examples",
                "strategy_profile_json",
                "total_char_budget",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=[
                "timeline_json",
                "source_timeline_json",
                "global_summary_json",
                "project_context_json",
                "style_guide",
                "style_examples",
                "strategy_profile_json",
                "total_char_budget",
            ],
        )
        self._system_prompt = (
            "你是中文影视解说主笔。"
            "你要先根据完整字幕时间轴写出连续、自然、有上下文承接的解说稿，"
            "再把每段解说回填到对应的 segment_id/start/end。"
        )

    def get_template(self) -> str:
        return """# 任务
你不是逐段机械改写器，而是影视解说主笔。请先阅读“整集原始字幕时间轴”，理解完整剧情、人名、因果和前后关系；再根据“剪辑回填时间轴”逐段输出解说。

# 写作原则
1. `source_timeline_json` 是整集原始字幕，负责完整理解；`timeline_json` 是最终剪辑回填窗口，负责输出分段。后续会直接用 `timeline_json` 的字幕 start/end 去切原片，所以不得改时间、不得跨段合并、不得丢段。
2. 字幕负责事实，已有 visual_evidence 只负责动作、表情、物件、场景质感；没有画面证据时不要编动作。
3. 不要复述字幕，不要照搬台词，不要连续照抄字幕 8 个以上汉字。
4. 禁止分析腔和模板腔：不要写“这一段主要交代”“这一段承担的是”“信息揭露功能”“推动矛盾升级”“观众会意识到”“真正麻烦在后面”。
5. 同一主题可以呼应，但不能重复同一句式；相邻段开头不能都用“这时/这里/话说到这里/真正”。
6. 每条解说必须对应自己的 segment_id 和 start/end 时间窗，不提前剧透后段，不回头总结上段。
7. 风格、节奏、字数服从 style_guide、style_examples 和每段 char_budget。总字数尽量控制在 `${total_char_budget}` 字以内。
8. 只输出 JSON，不要 Markdown，不要解释。

# 当前提示词策略
下面是本轮使用的写作策略。它不是文案库，不能照抄；它只告诉你应该怎么写、不要怎么写、哪些片段该加重。
${strategy_profile_json}

# 输出 JSON 结构
{
  "full_script": "把所有 narration 串起来后的完整解说稿，可选",
  "items": [
    {
      "segment_id": "输入中的 segment_id",
      "order": 1,
      "start": 0.0,
      "end": 5.0,
      "narration": "可直接配音的解说词",
      "sentences": [
        {
          "sentence_id": "s001",
          "text": "这一小句解说",
          "start": 0.0,
          "end": 2.5,
          "subtitle_ids": ["可选"],
          "char_budget": 28,
          "rewrite_intent": "这一句承担的口播目的"
        }
      ],
      "raw_voice_keep": false,
      "tone": "语气",
      "opening_type": "悬念/直叙/情绪推进/过渡",
      "risk_note": "证据不足时说明保守表达"
    }
  ]
}

# 项目上下文
${project_context_json}

# 全局剧情摘要
${global_summary_json}

# 整集原始字幕时间轴（用于完整理解，不是最终输出分段）
先完整阅读这里，再写解说。这里可以比剪辑窗口更细，不能因为它细就逐句复述字幕。
${source_timeline_json}

# 风格说明
如果这里出现“历史正剧深度解说｜通用AI提示词模板”，它就是本轮直接喂给 AI 的写作模板，必须按模板执行；同时仍要按 timeline_json 分段回填，不得丢段、串段或改 JSON 结构。
${style_guide}

# 风格样本
${style_examples}

# 剪辑回填时间轴 / 按时间轴排列的字幕/画面证据（最终必须一条不漏地按这些 segment_id 输出；后续直接用这些字幕时间切原片）
${timeline_json}
"""
