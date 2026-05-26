# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "suspense": {
        "label": "悬疑压迫型",
        "tone": "tense",
        "sentence_length": "short",
        "hook_density": "high",
        "humor": "low",
        "analysis_depth": "medium",
        "delivery": "短句、停顿、压低悬念，不提前泄底",
        "connectors": ["但很快", "可他不知道", "真正危险的，是"],
        "avoid_words": ["首先", "其次", "综上", "由此可见"],
    },
    "short_video_fast": {
        "label": "快节奏短视频型",
        "tone": "direct",
        "sentence_length": "short",
        "hook_density": "high",
        "humor": "medium",
        "analysis_depth": "low",
        "delivery": "信息密集、快速推进、少解释废话",
        "connectors": ["下一秒", "没想到", "更离谱的是"],
        "avoid_words": ["与此同时", "随后", "整个事件"],
    },
    "commentary_funny": {
        "label": "吐槽爽文型",
        "tone": "sarcastic",
        "sentence_length": "medium",
        "hook_density": "medium",
        "humor": "high",
        "analysis_depth": "low",
        "delivery": "轻微吐槽、爽点前置、不要太书面",
        "connectors": ["这下有意思了", "他以为稳了", "结果反手就被打脸"],
        "avoid_words": ["显而易见", "可以看出", "故事情节"],
    },
    "cinematic": {
        "label": "电影感解说型",
        "tone": "immersive",
        "sentence_length": "mixed",
        "hook_density": "medium",
        "humor": "low",
        "analysis_depth": "high",
        "delivery": "沉浸、克制、有因果和潜台词",
        "connectors": ["镜头到这里", "这一刻", "他的沉默已经说明了一切"],
        "avoid_words": ["非常", "十分", "然后"],
    },
    "warm_story": {
        "label": "温柔讲述型",
        "tone": "warm",
        "sentence_length": "mixed",
        "hook_density": "low",
        "humor": "low",
        "analysis_depth": "medium",
        "delivery": "舒缓、有共情、重人物情绪",
        "connectors": ["其实", "到这里", "他终于明白"],
        "avoid_words": ["爆炸", "炸裂", "杀疯了"],
    },
}

ALIASES = {
    "悬疑": "suspense",
    "悬疑解说": "suspense",
    "快节奏": "short_video_fast",
    "短视频": "short_video_fast",
    "吐槽": "commentary_funny",
    "爽文": "commentary_funny",
    "电影感": "cinematic",
    "电影": "cinematic",
    "温柔": "warm_story",
}


def normalize_style_key(style_key: str | None) -> str:
    key = (style_key or "suspense").strip()
    return ALIASES.get(key, key if key in STYLE_PROFILES else "suspense")


def get_style_profile(style_key: str | None = None) -> Dict[str, Any]:
    key = normalize_style_key(style_key)
    profile = deepcopy(STYLE_PROFILES[key])
    profile["style_key"] = key
    return profile


def list_style_profiles() -> List[Dict[str, Any]]:
    return [get_style_profile(k) for k in STYLE_PROFILES]
