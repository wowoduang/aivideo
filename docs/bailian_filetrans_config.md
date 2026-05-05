# Bailian Qwen3-ASR-Flash-Filetrans 配置说明

运行配置文件仍然以外置 workspace 为准：

`E:\aivideo-v5-workspace\state\config.toml`

`qwen3-asr-flash-filetrans` 是长音频异步转写模型，和 `qwen3-asr-flash` 的短音频同步接口不是一条链路。

关键区别：

- `qwen3-asr-flash` 可以直接传本地音频的 base64，适合短音频同步识别。
- `qwen3-asr-flash-filetrans` 必须提交公网可访问的 `file_url`，不能直接传本地 Windows 路径，也不能传 `127.0.0.1` / `localhost`。
- 本补丁会把抽取出的音频复制到 `workspace/frontend_uploads/asr_filetrans/`，然后用你配置的公网 base url 拼出可访问地址。

## 配置示例

在 `E:\aivideo-v5-workspace\state\config.toml` 的 `[whisper]` 下配置：

```toml
backend = "bailian"
bailian_api_key = "你的百炼 API Key"
bailian_region = "cn"
bailian_model = "qwen3-asr-flash-filetrans"
bailian_verify_ssl = false
bailian_strict_mode = true

# 这里必须是公网可访问地址，不能是 localhost/127.0.0.1。
# 例如用 ngrok/cpolar 把本地 18000 暴露出去后填写这个地址。
bailian_filetrans_public_base_url = "https://你的公网域名"

bailian_filetrans_timeout = 3600
bailian_filetrans_poll_interval = 2
bailian_filetrans_enable_words = true
```

## 本地测试方式

如果后端本地地址是：

`http://127.0.0.1:18000`

你需要用内网穿透得到公网地址，例如：

`https://xxxx.ngrok-free.app`

并确认公网能访问上传目录：

`https://xxxx.ngrok-free.app/uploads/asr_filetrans/xxx.mp3`

阿里云百炼服务器能访问这个 URL 后，filetrans 才能转写。

## 不要这样配置

不要把 `bailian_filetrans_public_base_url` 配成：

- `http://127.0.0.1:18000`
- `http://localhost:18000`
- `http://192.168.x.x:18000`
- 本地磁盘路径

这些地址只有你本机能访问，阿里云服务器访问不了，会返回 `url error, please check url`。
