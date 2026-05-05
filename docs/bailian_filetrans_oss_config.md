# 百炼 qwen3-asr-flash-filetrans + OSS 配置

运行时配置文件是外置 workspace 的：

`E:\aivideo-v5-workspace\state\config.toml`

`qwen3-asr-flash-filetrans` 不能读取本地路径，必须拿到百炼服务器可访问的音频 URL。生产推荐流程是：后端抽取音频 → 上传 OSS → 生成临时签名 URL → 提交百炼 filetrans 异步任务。

## 依赖

先安装 OSS SDK：

```powershell
pip install oss2
```

或者重新安装：

```powershell
pip install -r requirements.txt
```

## 配置示例

```toml
[whisper]
backend = "bailian"
bailian_model = "qwen3-asr-flash-filetrans"
bailian_region = "cn"
bailian_verify_ssl = false
bailian_strict_mode = true

# filetrans 专用
bailian_filetrans_audio_source = "oss"
bailian_filetrans_timeout = 3600
bailian_filetrans_poll_interval = 2
bailian_filetrans_enable_words = true

[oss]
endpoint = "https://oss-cn-beijing.aliyuncs.com"
bucket = "你的 bucket 名称"
access_key_id = "你的 AccessKeyId"
access_key_secret = "你的 AccessKeySecret"
# 如果用 STS 临时凭证，再填写 security_token
# security_token = ""
prefix = "aivideo/asr-filetrans"
url_expires = 7200
```

## 注意

- `endpoint` 和百炼地域尽量一致。国内百炼通常配国内 OSS，例如北京。
- Bucket 不需要公开；代码会生成临时签名 URL。
- `qwen3-asr-flash-filetrans` 只走 DashScope 异步转写接口，不走 OpenAI compatible。
- 如果日志仍提示 `url error, please check url`，说明百炼无法访问生成的 OSS URL，优先检查 bucket 权限、签名 URL 有效期、endpoint 和网络策略。
