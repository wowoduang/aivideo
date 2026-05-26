# frontend flow state machine fix v2

## 作用
修复前端项目流程状态串乱问题：

- 新建项目不再继承旧项目的字幕页/配置页/生成页状态。
- 刷新恢复只恢复“当前项目自己的合法阶段”。
- 没有视频时强制回到 upload，不允许进入字幕页空白预览。
- 有视频但没有字幕时，最多进入 subtitle，不允许进入 config/generate。
- 切换项目时清空旧项目的字幕、识别状态、生成进度、预览弹窗。
- 重新上传/裁剪视频后清空旧字幕路径，防止旧字幕对应旧视频。
- 刷新后已有服务端视频但 uploadedFile 为空时，仍允许进入字幕步骤。
- ProjectStatus 增加 failed 的前端显示，避免状态映射缺失。

## 使用
在源码根目录执行：

```powershell
cd E:\aivideo-v5
python apply_frontend_flow_fix_v2.py
cd web
npm run build
```

## 修改文件

- `web/src/lib/project-flow.ts` 新增轻量流程状态机。
- `web/src/pages/editor/Material.tsx` 统一 `normalizePhase / canEnterPhase / goPhase`。
- `web/src/components/workspace/VideoUploadStep.tsx` 支持服务端视频恢复后的下一步判断。
- `web/src/components/workspace/SubtitleStep.tsx` 增加无视频空状态保护。
- `web/src/pages/Projects.tsx` 补全 failed 状态显示。

## 我在沙盒里做过的检查

- 解压了你上传的完整源码 zip。
- 对当前源码进行了静态流程分析。
- 用独立 JS 跑了核心状态机用例：
  - 新项目/无视频/currentStep=subtitle => upload
  - 无视频/currentStep=config => upload
  - 有视频/无字幕/currentStep=config => subtitle
  - 有视频/有字幕/currentStep=config => config
  - 有视频/有字幕/currentStep=generate => generate

说明：沙盒里 `npm ci` 安装依赖超时，所以没有完成完整 Vite build。补丁脚本会保留备份，便于本地回滚。
