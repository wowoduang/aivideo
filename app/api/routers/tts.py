from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.utils import utils


router = APIRouter(prefix="/tts", tags=["tts"])


def _voice_api():
    try:
        from app.services.voice import (
            get_all_azure_voices,
            should_use_azure_speech_services,
            tts as tts_synthesize,
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"missing_optional_dependency:{exc.name}") from exc

    return {
        "get_all_azure_voices": get_all_azure_voices,
        "should_use_azure_speech_services": should_use_azure_speech_services,
        "tts_synthesize": tts_synthesize,
    }


# 常见 zh-CN edge_tts 音色的中文友好名，没命中的就用 Neural 前缀
_ZH_CN_FRIENDLY_NAMES = {
    "Xiaoxiao": "晓晓",
    "Yunxi": "云希",
    "Yunjian": "云健",
    "Xiaoyi": "晓伊",
    "Yunyang": "云扬",
    "Xiaochen": "晓辰",
    "Xiaohan": "晓涵",
    "Xiaomeng": "晓梦",
    "Xiaomo": "晓墨",
    "Xiaoqiu": "晓秋",
    "Xiaorui": "晓睿",
    "Xiaoshuang": "晓双",
    "Xiaoxuan": "晓萱",
    "Xiaoyan": "晓颜",
    "Xiaoyou": "晓悠",
    "Xiaozhen": "晓甄",
    "Yunfeng": "云枫",
    "Yunhao": "云浩",
    "Yunxia": "云夏",
    "Yunye": "云野",
    "Yunze": "云泽",
    "YunxiaoMultilingual": "云枭 (多语)",
    "XiaoxiaoMultilingual": "晓晓 (多语)",
}


class TtsVoice(BaseModel):
    id: str
    display_name: str
    locale: str
    gender: str
    engine: str
    tier: str  # "basic" / "premium"


class TtsVoicesResponse(BaseModel):
    voices: List[TtsVoice]
    default_engine: str


def _parse_voice_entry(entry: str) -> Optional[TtsVoice]:
    # 形如：zh-CN-XiaoxiaoNeural-Female / zh-CN-XiaoxiaoMultilingualNeural-V2-Female
    parts = entry.rsplit("-", 1)
    if len(parts) != 2:
        return None
    name, gender = parts
    if gender not in {"Female", "Male"}:
        return None

    tokens = name.split("-")
    if len(tokens) < 3:
        return None
    locale = "-".join(tokens[:2])
    is_v2 = name.endswith("-V2")
    neural_name = tokens[2].replace("Neural", "")
    # Multilingual-V2 结尾会多一个 token
    if is_v2 and len(tokens) >= 4:
        neural_name = tokens[2].replace("Neural", "")

    display = _ZH_CN_FRIENDLY_NAMES.get(neural_name, neural_name)
    if is_v2 and "(多语)" not in display:
        display = f"{display} (V2)"

    return TtsVoice(
        id=entry,
        display_name=display,
        locale=locale,
        gender="女" if gender == "Female" else "男",
        engine="azure_speech" if is_v2 else "edge_tts",
        tier="premium" if is_v2 else "basic",
    )


@router.get("/voices", response_model=TtsVoicesResponse)
def list_voices(locales: str = "zh-CN,en-US"):
    locale_filter = [s.strip() for s in (locales or "").split(",") if s.strip()]
    entries = _voice_api()["get_all_azure_voices"](filter_locals=locale_filter or None)
    voices: List[TtsVoice] = []
    for entry in entries:
        parsed = _parse_voice_entry(entry)
        if parsed is not None:
            voices.append(parsed)
    # zh-CN 优先
    voices.sort(key=lambda v: (0 if v.locale == "zh-CN" else 1, v.tier, v.display_name))
    return TtsVoicesResponse(voices=voices, default_engine="edge_tts")


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice_name: str = Field(..., min_length=1)
    voice_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    voice_pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    tts_engine: str = Field(default="", description="留空自动选择 edge_tts / azure_speech")


class TtsSynthesizeResponse(BaseModel):
    path: str
    url: str
    filename: str
    size: int


def _sanitize_text(text: str) -> str:
    # 去除 SRT/脚本里常见的时间戳 / 序号行，避免合成时把它们念出来
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+$", stripped):
            continue
        if "-->" in stripped and re.search(r"\d+:\d+:\d+", stripped):
            continue
        lines.append(stripped)
    return " ".join(lines).strip()


@router.post("/synthesize", response_model=TtsSynthesizeResponse)
def synthesize(payload: TtsSynthesizeRequest):
    text = _sanitize_text(payload.text)
    if not text:
        raise HTTPException(status_code=400, detail="text_is_empty")

    engine = payload.tts_engine.strip().lower()
    if not engine:
        engine = "azure_speech" if _voice_api()["should_use_azure_speech_services"](payload.voice_name) else "edge_tts"

    out_dir = Path(utils.workspace_dir()) / "frontend_uploads" / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.mp3"
    out_path = out_dir / filename

    try:
        sub = _voice_api()["tts_synthesize"](
            text=text,
            voice_name=payload.voice_name,
            voice_rate=payload.voice_rate,
            voice_pitch=payload.voice_pitch,
            voice_file=str(out_path),
            tts_engine=engine,
        )
    except Exception as err:  # noqa: BLE001
        logger.exception("tts synthesize failed")
        raise HTTPException(status_code=500, detail=f"tts_failed: {err}") from err

    if not out_path.exists() or out_path.stat().st_size == 0:
        _ = sub  # sub 可能返回，但仍可能没写入音频文件（V2 等）
        raise HTTPException(status_code=500, detail="tts_no_audio_output")

    size = out_path.stat().st_size
    return TtsSynthesizeResponse(
        path=str(out_path),
        url=f"/uploads/tts/{filename}",
        filename=filename,
        size=size,
    )
