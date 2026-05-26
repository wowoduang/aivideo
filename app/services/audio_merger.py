import os
import json
import subprocess
import edge_tts
from edge_tts import submaker
from pydub import AudioSegment
from typing import List, Dict
from loguru import logger
from app.utils import utils


def check_ffmpeg():
    """检查FFmpeg是否已安装"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def _fit_tts_audio_to_segment(tts_audio: AudioSegment, target_duration_seconds: float) -> AudioSegment:
    # 防止一段 TTS 过长覆盖到下一段；同时提高解说响度。
    target_ms = int(max(float(target_duration_seconds or 0.0), 0.2) * 1000)
    if target_ms <= 0:
        return tts_audio

    tts_audio = tts_audio + 4

    if len(tts_audio) <= target_ms:
        return tts_audio

    try:
        from pydub import effects
        ratio = len(tts_audio) / max(target_ms, 1)
        if 1.03 < ratio <= 1.35 and target_ms > 1000:
            tts_audio = effects.speedup(tts_audio, playback_speed=ratio, chunk_size=80, crossfade=20)
    except Exception as exc:
        logger.warning(f"TTS 轻微加速失败，改用裁剪: {exc}")

    if len(tts_audio) > target_ms:
        logger.warning(f"TTS 超出片段时长，将裁剪: tts={len(tts_audio)/1000:.2f}s, segment={target_ms/1000:.2f}s")
        fade_ms = min(220, max(60, target_ms // 8))
        tts_audio = tts_audio[:target_ms].fade_out(fade_ms)

    return tts_audio


def merge_audio_files(task_id: str, total_duration: float, list_script: list):
    """
    合并音频文件
    
    Args:
        task_id: 任务ID
        total_duration: 总时长
        list_script: 完整脚本信息，包含duration时长和audio路径
    
    Returns:
        str: 合并后的音频文件路径
    """
    # 检查FFmpeg是否安装
    if not check_ffmpeg():
        logger.error("FFmpeg未安装，无法合并音频文件")
        return None

    # 创建一个空的音频片段
    final_audio = AudioSegment.silent(duration=total_duration * 1000)  # 总时长以毫秒为单位

    # 计算每个片段的开始位置（基于duration字段）
    current_position = 0  # 初始位置（秒）
    
    # 遍历脚本中的每个片段
    for segment in list_script:
        try:
            # 获取片段时长（秒）
            duration = segment['duration']
            
            # 检查audio字段是否为空
            if segment['audio'] and os.path.exists(segment['audio']):
                # 加载TTS音频文件
                tts_audio = AudioSegment.from_file(segment['audio'])
                
                # 将TTS音频添加到最终音频
                final_audio = final_audio.overlay(tts_audio, position=current_position * 1000)
            else:
                # audio为空，不添加音频，仅保留间隔
                logger.info(f"片段 {segment.get('timestamp', '')} 没有音频文件，保留 {duration} 秒的间隔")
            
            # 更新下一个片段的开始位置
            current_position += duration

        except Exception as e:
            logger.error(f"处理音频片段时出错: {str(e)}")
            # 即使处理失败，也要更新位置，确保后续片段位置正确
            if 'duration' in segment:
                current_position += segment['duration']
            continue

    # 保存合并后的音频文件
    output_audio_path = os.path.join(utils.task_dir(task_id), "merger_audio.mp3")
    final_audio.export(output_audio_path, format="mp3")
    logger.info(f"合并后的音频文件已保存: {output_audio_path}")

    return output_audio_path


def time_to_seconds(time_str):
    """
    将时间字符串转换为秒数，支持多种格式：
    1. 'HH:MM:SS,mmm' (时:分:秒,毫秒)
    2. 'MM:SS,mmm' (分:秒,毫秒)
    3. 'SS,mmm' (秒,毫秒)
    """
    try:
        # 处理毫秒部分
        if ',' in time_str:
            time_part, ms_part = time_str.split(',')
            ms = float(ms_part) / 1000
        else:
            time_part = time_str
            ms = 0

        # 分割时间部分
        parts = time_part.split(':')

        if len(parts) == 3:  # HH:MM:SS
            h, m, s = map(int, parts)
            seconds = h * 3600 + m * 60 + s
        elif len(parts) == 2:  # MM:SS
            m, s = map(int, parts)
            seconds = m * 60 + s
        else:  # SS
            seconds = int(parts[0])

        return seconds + ms
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing time {time_str}: {str(e)}")
        return 0.0


def extract_timestamp(filename):
    """
    从文件名中提取开始和结束时间戳
    例如: "audio_00_06,500-00_24,800.mp3" -> (6.5, 24.8)
    """
    try:
        # 从文件名中提取时间部分
        time_part = filename.split('_', 1)[1].split('.')[0]  # 获取 "00_06,500-00_24,800" 部分
        start_time, end_time = time_part.split('-')  # 分割成开始和结束时间

        # 将下划线格式转换回冒号格式
        start_time = start_time.replace('_', ':')
        end_time = end_time.replace('_', ':')

        # 将时间戳转换为秒
        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time)

        return start_seconds, end_seconds
    except Exception as e:
        logger.error(f"Error extracting timestamp from {filename}: {str(e)}")
        return 0.0, 0.0


if __name__ == "__main__":
    print("Use merge_audio_files() with workspace task audio outputs; legacy local-path demo data has been removed.")
