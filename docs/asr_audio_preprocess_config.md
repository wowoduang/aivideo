# ASR audio preprocessing config

Runtime config file:

`E:\aivideo-v5-workspace\state\config.toml`

Recommended settings under `[whisper]`:

```toml
# Use lossless audio for ASR input instead of low-bitrate MP3.
asr_audio_format = "wav"
audio_sample_rate = 16000
audio_channels = 1

# Keep this enabled for speech-oriented normalization before ASR.
asr_audio_enable_filter = true
asr_audio_filter = "highpass=f=80,lowpass=f=7600,loudnorm=I=-16:TP=-1.5:LRA=11"

# Optional fallback if you intentionally want compressed audio.
asr_audio_mp3_bitrate = "128k"
```

What changed:
- ASR extraction now defaults to WAV PCM instead of low-bitrate MP3.
- Audio is resampled to mono 16 kHz by default.
- A speech-friendly ffmpeg filter is applied before ASR.
- If filtered extraction fails, it automatically retries without the filter.
- This affects audio sent to Bailian, Whisper, SenseVoice/FunASR, and external backends that consume the extracted audio.
