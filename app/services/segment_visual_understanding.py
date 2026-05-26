# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from app.config import config as app_config
except Exception:
    app_config = None


def _get_cfg(key: str, default: Any = None) -> Any:
    cfg = app_config
    if cfg is None:
        return default
    app = getattr(cfg, "app", None)
    if isinstance(app, dict) and key in app:
        return app.get(key, default)
    if app is not None and hasattr(app, key):
        return getattr(app, key, default)
    if hasattr(cfg, key):
        return getattr(cfg, key, default)
    try:
        if isinstance(cfg, dict):
            if key in cfg:
                return cfg.get(key, default)
            if isinstance(cfg.get("app"), dict):
                return cfg["app"].get(key, default)
    except Exception as _e:
        logger.debug("配置字段 {} 读取失败: {}", key, _e)
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _model_for_openai_compatible(raw: str) -> str:
    model = str(raw or "").strip()
    if model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _vision_settings() -> Dict[str, Any]:
    return {
        # Old Native Runtime visual-card enrichment is not part of the active
        # movie_story mainflow. Formal two_round_visual prepares first-round
        # evidence in app.services.movie_story.two_round_visual_narration.
        "enabled": _as_bool(_get_cfg("enable_segment_visual_understanding", False), False),
        "rewrite": _as_bool(_get_cfg("visual_understanding_rewrite_narration", True), True),
        "max_segments": _safe_int(_get_cfg("visual_understanding_max_segments", 30), 30),
        "max_frames": _safe_int(_get_cfg("visual_understanding_max_frames_per_segment", 4), 4),
        "base_url": str(_get_cfg("vision_litellm_base_url", "") or "").rstrip("/"),
        "api_key": str(_get_cfg("vision_litellm_api_key", "") or ""),
        "model": _model_for_openai_compatible(str(_get_cfg("vision_litellm_model_name", "") or "")),
        "timeout": _safe_int(_get_cfg("visual_understanding_timeout", 120), 120),
    }


def _text_settings() -> Dict[str, Any]:
    base_url = str(_get_cfg("text_litellm_base_url", "") or "").rstrip("/")
    api_key = str(_get_cfg("text_litellm_api_key", "") or "")
    model = _model_for_openai_compatible(str(_get_cfg("text_litellm_model_name", "") or ""))
    if not base_url:
        base_url = str(_get_cfg("vision_litellm_base_url", "") or "").rstrip("/")
    if not api_key:
        api_key = str(_get_cfg("vision_litellm_api_key", "") or "")
    if not model:
        model = _model_for_openai_compatible(str(_get_cfg("vision_litellm_model_name", "") or ""))
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout": _safe_int(_get_cfg("text_rewrite_timeout", 120), 120),
    }


def _chat_url(base_url: str) -> str:
    base = str(base_url or "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception as _e:
        logger.debug("JSON 解析失败: {}", _e)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _post_chat(settings: Dict[str, Any], messages: List[Dict[str, Any]], temperature: float = 0.2) -> str:
    url = _chat_url(settings.get("base_url", ""))
    api_key = settings.get("api_key", "")
    model = settings.get("model", "")
    if not url or not api_key or not model:
        raise RuntimeError("视觉/文本模型配置不完整：缺少 base_url、api_key 或 model")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=int(settings.get("timeout") or 120))
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM 调用失败: status={resp.status_code}, body={resp.text[:600]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _resize_and_encode_image(path: str, max_side: int = 960, quality: int = 82) -> Optional[str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        if Image is None:
            raw = p.read_bytes()
            suffix = p.suffix.lower().lstrip(".") or "jpeg"
            mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
            return f"data:image/{mime};base64," + base64.b64encode(raw).decode("ascii")
        with Image.open(p) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, float(max_side) / max(w, h))
            if scale < 1.0:
                im = im.resize((int(w * scale), int(h * scale)))
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logger.warning("代表帧编码失败: path={}, error={}", path, exc)
        return None


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        v = str(value or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _collect_frame_paths(segment: Dict[str, Any], max_frames: int) -> List[str]:
    paths: List[str] = []

    def add(value: Any) -> None:
        if not value:
            return
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, dict):
            p = value.get("frame_path") or value.get("path") or value.get("frame") or value.get("image")
            if p:
                paths.append(str(p))

    for key in ("frame_paths", "frames"):
        for item in segment.get(key) or []:
            add(item)
    for key in ("representative_frames", "visual_summary", "sampled_frames"):
        for item in segment.get(key) or []:
            add(item)
    for key in ("frame_path", "cover_frame", "representative_frame"):
        add(segment.get(key))
    return _dedupe(paths)[:max_frames]


def _segment_text(segment: Dict[str, Any]) -> str:
    parts = [
        segment.get("main_text_evidence"),
        segment.get("subtitle_text"),
        segment.get("source_text"),
        segment.get("surface_dialogue_meaning"),
        segment.get("real_narrative_state"),
        segment.get("narrative_function"),
        segment.get("reason"),
    ]
    return "\n".join(str(x) for x in parts if x)


def _segment_id(segment: Dict[str, Any]) -> str:
    return str(
        segment.get("segment_id")
        or segment.get("scene_id")
        or segment.get("highlight_id")
        or segment.get("_id")
        or segment.get("id")
        or ""
    )


def _time_hint(segment: Dict[str, Any]) -> str:
    return str(
        segment.get("timestamp")
        or segment.get("semantic_timestamp")
        or segment.get("time_range")
        or f"{segment.get('start', '')}-{segment.get('end', '')}"
    )


def _should_visual_analyze(segment: Dict[str, Any]) -> bool:
    if segment.get("need_visual_verify") is True:
        return True
    if str(segment.get("importance_level", "")).lower() == "high":
        return True
    if segment.get("llm_highlight_selected") is True:
        return True
    if segment.get("selected") is True:
        return True
    if _collect_frame_paths(segment, 1):
        return True
    return False


def _compact_global_summary(global_summary: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(global_summary, dict):
        return {}
    keys = [
        "protagonist",
        "story_arc",
        "major_turning_points",
        "character_relations",
        "entity_map",
        "global_summary",
        "video_title",
        "full_subtitle_understanding",
    ]
    out = {k: global_summary.get(k) for k in keys if k in global_summary}
    text = json.dumps(out, ensure_ascii=False)
    if len(text) > 3500:
        return {"summary_excerpt": text[:3500]}
    return out


def build_visual_prompt(segment: Dict[str, Any], global_summary: Dict[str, Any]) -> str:
    return f"""
你是影视解说系统里的“片段视觉理解与字幕校验员”。你不是重新写整部剧情，而是给字幕优先链路补充当前片段画面证据。

硬规则：
1. 只分析当前片段，允许前后 2-3 秒误差，不得把前后剧情写进当前段。
2. 字幕是剧情主线；画面用于确认人物、动作、表情、场景、情绪，以及修正字幕字面误读。
3. 只写画面能看到或由字幕+画面共同支持的信息。
4. 心理推断必须给 evidence。证据不足时写“无法确定”，或用“像是/似乎/仿佛”。
5. 不要把 ASR 错字当新人名；“虫八/冲八/虫爸/崇八”等按“重八/朱重八”理解。
6. 如果画面与字幕不一致，明确说明 conflict，不要强行编。
7. 只输出 JSON，不要 Markdown。

当前片段时间窗：
{_time_hint(segment)}

全局剧情摘要：
{json.dumps(_compact_global_summary(global_summary), ensure_ascii=False)[:3500]}

当前片段字幕/剧情证据：
{_segment_text(segment)[:4500]}

请输出 JSON，字段必须完整：
{{
  "segment_id": "{_segment_id(segment)}",
  "visible_characters": ["画面能确认的人物；不能确认写未知"],
  "character_alias_resolution": {{"虫八/冲爸/虫爸等": "重八/朱重八"}},
  "observable_actions": ["只写画面能看到的动作，例如低头、掏东西、沉默、转身、递物、跪下"],
  "facial_expression": ["表情、眼神、姿态，例如紧绷、回避、迟疑、强装镇定"],
  "scene_environment": "场景、地点、光线、氛围",
  "visual_emotion": "画面整体情绪",
  "subtitle_visual_alignment": "aligned|partially_aligned|conflict|uncertain",
  "visual_correction": "画面对字幕理解的修正；无则写无",
  "psychological_inference": {{
    "text": "心理推断；证据不足写无法确定",
    "confidence": 0.0,
    "evidence": ["支持心理判断的画面证据和字幕证据"]
  }},
  "speakable_points": ["解说可以安全使用的贴画面点"],
  "do_not_say": ["当前片段不能说的内容，包括无证据心理、前后段事件、错误人名"],
  "narration_rewrite_hint": "一句贴画面解说建议",
  "clip_match_risk": "low|medium|high",
  "confidence": 0.0
}}
""".strip()


def _normalize_card(card: Dict[str, Any], segment: Dict[str, Any], frame_paths: List[str]) -> Dict[str, Any]:
    if not isinstance(card, dict):
        card = {}
    psych = card.get("psychological_inference")
    if not isinstance(psych, dict):
        psych = {"text": "无法确定", "confidence": 0.0, "evidence": []}

    def list_field(key: str) -> List[str]:
        value = card.get(key)
        if isinstance(value, list):
            return [str(x) for x in value if str(x).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    return {
        "status": card.get("status", "ok"),
        "segment_id": str(card.get("segment_id") or _segment_id(segment)),
        "time_hint": _time_hint(segment),
        "frame_paths": frame_paths,
        "visible_characters": list_field("visible_characters"),
        "character_alias_resolution": card.get("character_alias_resolution") or {},
        "observable_actions": list_field("observable_actions"),
        "facial_expression": list_field("facial_expression"),
        "scene_environment": str(card.get("scene_environment") or ""),
        "visual_emotion": str(card.get("visual_emotion") or ""),
        "subtitle_visual_alignment": str(card.get("subtitle_visual_alignment") or "uncertain"),
        "visual_correction": str(card.get("visual_correction") or "无"),
        "psychological_inference": {
            "text": str(psych.get("text") or "无法确定"),
            "confidence": float(psych.get("confidence") or 0.0),
            "evidence": psych.get("evidence") if isinstance(psych.get("evidence"), list) else [],
        },
        "speakable_points": list_field("speakable_points"),
        "do_not_say": list_field("do_not_say"),
        "narration_rewrite_hint": str(card.get("narration_rewrite_hint") or ""),
        "clip_match_risk": str(card.get("clip_match_risk") or "medium"),
        "confidence": float(card.get("confidence") or 0.0),
    }


def analyze_segment_visual(segment: Dict[str, Any], global_summary: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    frame_paths = _collect_frame_paths(segment, int(settings.get("max_frames") or 4))
    images = []
    valid_paths = []
    for p in frame_paths:
        data_url = _resize_and_encode_image(p)
        if data_url:
            valid_paths.append(p)
            images.append({"type": "image_url", "image_url": {"url": data_url}})
    if not images:
        return _normalize_card(
            {
                "status": "no_frames",
                "subtitle_visual_alignment": "uncertain",
                "clip_match_risk": "medium",
                "narration_rewrite_hint": "",
                "do_not_say": ["没有代表帧，不能写具体表情和动作"],
            },
            segment,
            frame_paths,
        )

    content: List[Dict[str, Any]] = [{"type": "text", "text": build_visual_prompt(segment, global_summary)}]
    content.extend(images)
    messages = [
        {"role": "system", "content": "你是严格的影视片段视觉理解与字幕校验员，只输出 JSON。"},
        {"role": "user", "content": content},
    ]
    raw = _post_chat(settings, messages, temperature=0.1)
    obj = _extract_json_object(raw)
    if not obj:
        raise RuntimeError("视觉模型未返回有效 JSON")
    obj["status"] = "ok"
    return _normalize_card(obj, segment, valid_paths)


def enrich_scene_evidence_with_visual_cards(scene_evidence: List[Dict[str, Any]], global_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    settings = _vision_settings()
    if not settings.get("enabled"):
        logger.info("片段视觉理解已关闭")
        return scene_evidence
    if not settings.get("api_key") or not settings.get("base_url") or not settings.get("model"):
        logger.warning("片段视觉理解跳过：vision_litellm 配置不完整")
        return scene_evidence

    max_segments = int(settings.get("max_segments") or 30)
    enriched: List[Dict[str, Any]] = []
    analyzed = 0

    for seg in scene_evidence or []:
        item = dict(seg)
        if analyzed < max_segments and _should_visual_analyze(item):
            try:
                card = analyze_segment_visual(item, global_summary, settings)
                item["segment_visual_card"] = card
                item["visual_evidence_pack"] = {
                    "segment_id": card.get("segment_id"),
                    "time_hint": card.get("time_hint"),
                    "subtitle_evidence": _segment_text(item),
                    "visual_card": card,
                }
                item["visual_understanding_status"] = card.get("status", "ok")
                analyzed += 1
                logger.info(
                    "片段视觉理解完成: segment={}, risk={}, alignment={}, confidence={}",
                    _segment_id(item),
                    card.get("clip_match_risk"),
                    card.get("subtitle_visual_alignment"),
                    card.get("confidence"),
                )
                time.sleep(0.2)
            except Exception as exc:
                logger.warning("片段视觉理解失败: segment={}, error={}", _segment_id(item), exc)
                item["segment_visual_card"] = {
                    "status": "failed",
                    "error": str(exc),
                    "segment_id": _segment_id(item),
                    "time_hint": _time_hint(item),
                }
                item["visual_understanding_status"] = "failed"
        enriched.append(item)

    logger.info("片段视觉理解批处理完成: analyzed={}, total={}", analyzed, len(enriched))
    return enriched


def _build_card_index(scene_evidence: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for seg in scene_evidence or []:
        card = seg.get("segment_visual_card")
        if not isinstance(card, dict) or card.get("status") not in {"ok", "no_frames"}:
            continue
        keys = [
            seg.get("segment_id"),
            seg.get("scene_id"),
            seg.get("highlight_id"),
            seg.get("_id"),
            seg.get("id"),
            card.get("segment_id"),
            _segment_id(seg),
        ]
        for key in keys:
            if key is not None and str(key).strip():
                index[str(key)] = card
    return index


def _find_visual_card_for_script(item: Dict[str, Any], card_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    keys: List[str] = []
    for key in ("segment_id", "scene_id", "highlight_id", "_id", "id"):
        value = item.get(key)
        if value is not None:
            keys.append(str(value))
    for key in item.get("source_segment_ids") or []:
        keys.append(str(key))
    for key in keys:
        if key in card_index:
            return card_index[key]
    return None


def _rewrite_prompt(item: Dict[str, Any], card: Dict[str, Any], global_summary: Dict[str, Any]) -> str:
    budget = int(item.get("char_budget") or 80)
    strategy = item.get("prompt_strategy_profile") if isinstance(item.get("prompt_strategy_profile"), dict) else {}
    return f"""
你是影视解说改写员。你的任务是让解说更贴当前画面，而不是改写成剧情摘要。

硬规则：
1. 只讲当前片段，允许前后 2-3 秒误差，不讲前后段。
2. 字幕负责剧情主线，视觉卡片负责动作、表情、情绪、心理证据。
3. 必须优先使用 visual_card.speakable_points / observable_actions / facial_expression。
4. 不得使用 visual_card.do_not_say 中的内容。
5. 心理描写必须来自 psychological_inference.evidence。
6. confidence < 0.65 时，心理只能写“像是/似乎/仿佛/显得”，不能写成确定事实。
7. 如果 visual_card.status=no_frames 或 alignment=uncertain，只能保守改写。
8. 中文短视频解说风格，{max(20, budget - 20)} 到 {budget + 20} 个汉字左右。
9. 如果原解说包含 narration_sentences，尽量维持句子级时间轴，不要把一句扩成无法卡画面的长段。
10. 当前策略只指导写法，不是文案库，不能照抄策略里的句子。
11. 只输出 JSON。

当前写作策略：
{json.dumps(strategy, ensure_ascii=False)[:1800]}

输出格式：
{{
  "narration": "改写后的解说",
  "sentences": [
    {{"sentence_id": "沿用原句ID或新ID", "text": "改写后小句", "start": 0.0, "end": 0.0, "visual_used": ["..."]}}
  ],
  "reason": "为什么这样改",
  "visual_used": ["使用了哪些画面证据"],
  "psychology_used": true,
  "risk": "low|medium|high"
}}

全局上下文：
{json.dumps(_compact_global_summary(global_summary), ensure_ascii=False)[:1600]}

当前字幕证据：
{str(item.get("main_text_evidence") or item.get("subtitle_text") or item.get("originalSubtitle") or "")[:2200]}

原解说：
{item.get("narration") or item.get("new_content") or item.get("content") or ""}

原句子级时间轴：
{json.dumps(item.get("narration_sentences") or [], ensure_ascii=False)[:1800]}

视觉卡片：
{json.dumps(card, ensure_ascii=False)[:3500]}
""".strip()


def refine_script_items_with_visual_cards(
    script_items: List[Dict[str, Any]],
    scene_evidence: List[Dict[str, Any]],
    global_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    settings = _vision_settings()
    if not settings.get("rewrite"):
        return script_items
    text_settings = _text_settings()
    if not text_settings.get("api_key") or not text_settings.get("base_url") or not text_settings.get("model"):
        logger.warning("视觉辅助解说改写跳过：text_litellm 配置不完整")
        return script_items

    card_index = _build_card_index(scene_evidence)
    if not card_index:
        logger.info("视觉辅助解说改写跳过：没有可用视觉卡片")
        return script_items

    refined: List[Dict[str, Any]] = []
    changed = 0
    report: List[Dict[str, Any]] = []

    for item in script_items or []:
        row = dict(item)
        card = _find_visual_card_for_script(row, card_index)
        if not card:
            row.setdefault("visual_refine", {"enabled": False, "reason": "no_matching_visual_card"})
            refined.append(row)
            continue

        try:
            messages = [
                {"role": "system", "content": "你是严格的影视解说改写员，只输出 JSON。"},
                {"role": "user", "content": _rewrite_prompt(row, card, global_summary)},
            ]
            raw = _post_chat(text_settings, messages, temperature=0.35)
            obj = _extract_json_object(raw)
            rewritten = str(obj.get("narration") or "").strip()

            if rewritten:
                old = row.get("narration", "")
                row["narration_before_visual_refine"] = old
                row["narration"] = rewritten
                if isinstance(obj.get("sentences"), list):
                    row["narration_sentences_before_visual_refine"] = row.get("narration_sentences") or []
                    row["narration_sentences"] = obj.get("sentences") or []
                row["visual_refine"] = {
                    "enabled": True,
                    "reason": obj.get("reason", ""),
                    "visual_used": obj.get("visual_used", []),
                    "psychology_used": bool(obj.get("psychology_used", False)),
                    "risk": obj.get("risk", "medium"),
                    "card": card,
                }
                changed += 1
                report.append({
                    "id": row.get("_id") or row.get("id"),
                    "before": old,
                    "after": rewritten,
                    "visual_used": obj.get("visual_used", []),
                    "risk": obj.get("risk", "medium"),
                })
        except Exception as exc:
            logger.warning("视觉辅助解说改写失败: id={}, error={}", row.get("_id") or row.get("id"), exc)
            row["visual_refine"] = {"enabled": False, "error": str(exc), "card": card}

        refined.append(row)

    logger.info("视觉辅助解说改写完成: changed={}, total={}", changed, len(refined))
    if refined:
        refined[0].setdefault("visual_refine_report_summary", {"changed": changed, "items": report[:50]})
    return refined


def collect_visual_audit(scene_evidence: List[Dict[str, Any]], script_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    cards = []
    for seg in scene_evidence or []:
        card = seg.get("segment_visual_card")
        if isinstance(card, dict):
            cards.append({
                "segment_id": _segment_id(seg),
                "timestamp": _time_hint(seg),
                "card": card,
            })

    refine = []
    for item in script_items or []:
        if isinstance(item.get("visual_refine"), dict):
            refine.append({
                "id": item.get("_id") or item.get("id"),
                "timestamp": item.get("timestamp"),
                "before": item.get("narration_before_visual_refine"),
                "after": item.get("narration"),
                "visual_refine": item.get("visual_refine"),
            })

    return {
        "visual_cards_count": len(cards),
        "visual_refine_count": sum(1 for x in refine if x.get("visual_refine", {}).get("enabled")),
        "visual_cards": cards,
        "visual_refine": refine,
    }


def write_visual_audit_files(output_dir: str | Path, scene_evidence: List[Dict[str, Any]], script_items: List[Dict[str, Any]]) -> None:
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        audit = collect_visual_audit(scene_evidence, script_items)
        (out / "movie_story_visual_cards.json").write_text(
            json.dumps(audit.get("visual_cards", []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out / "movie_story_visual_refine_report.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("视觉理解审计文件已写入: {}", out)
    except Exception as exc:
        logger.warning("写入视觉理解审计文件失败: {}", exc)
