# movie_story legacy archive

本目录保存已经移出正式主流程的历史代码。

## selected_highlight_visual_evidence_workflow.py

该 workflow 是 AI 曾经误实现的 selected-highlight 后置视觉证据链：
先生成 script/highlights，再对 selected highlights 抽帧、生成复核证据包。

当前正式 `two_round_visual` 定义是：第一轮多模态 prompt 前完成本地视觉证据准备，
第一轮多模态理解，第二轮文本写作，第二轮后直接进入剪辑/导出。

本轮没有迁移该 workflow 中的代码，因为它围绕后置复核设计，
不服务第一轮前的成本受控视觉证据准备。若未来需要 contact sheet 或路径命名能力，
应重新按正式模块边界抽取，不得从主流程直接 import 本归档文件。

同目录下的 *.py.archived 是旧 API 测试源，仅用于人工考古；
它们不应被 pytest 收集，也不得通过补 compatibility wrapper 恢复。
