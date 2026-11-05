# 阅读排版修复 Implementation Plan

**Goal:** 修复法规目录横排、PDF 硬换行与空白、过大的页码标题，并保留可核对的原件、原始资料及条款锚点。

**Architecture:** 不修改原始 Markdown、哈希、检索索引或专业审核状态。阅读界面采用宽正文与单侧栏；PDF 原件优先、提取文字辅助检索；安全 DOM 重建后仅做展示排版。用户已要求直接修复，不增加设计审批环节。

**Tech Stack:** Flask / Waitress、原生 JavaScript / CSS、unittest + Node、Playwright CLI。

## 1. 复现与边界

- [x] 对照用户截图与 CH01-S001、CH02-S006：网页段落内的目录换行被 HTML 合并；提取段落 pre-wrap 保留排版空格与硬换行；页码使用正文大标题样式。
- [x] 保留来源、正文内容、章节/条款/段落 ID；不靠 AI 改写法律文本。
- [x] 同时诊断用户打不开临时网址的问题，与 UI 修复分开验证；禁止改全局网络设置。旧隧道已退出，旧域名返回 502；指向新版 5002 的新隧道启动被工具策略拒绝，公网新版尚未交付。

## 2. 安全原件模式与回退

Files: `src/airworthiness/web/static/hall-reader.js`, new `hall-document-view.js`, `src/airworthiness/app.py`, `tests/test_reader_layout.py`, `tests/test_pdf_frame_security.py`.

- [x] 先写并运行失败测试：本地原件只允许固定同源接口；含 PDF 默认原件，无原件使用文字；查询或条款 hash 强制可见文字。原件主文/附录分别选择已实测；预览失败时仍保留新窗口原件与官方链接，采用手动降级。
- [x] 成功 PDF 响应 `frame-ancestors 'self'`，其他响应仍 `'none'`；不得引入任意远程 iframe。
- [x] 提取文字标明仅辅助检索，可切换“自动换行 / 保留提取换行”，不重排表格为虚构结构。

## 3. 阅读排版

Files: `hall-content.js`, `hall-reader.js`, `hall.css`, `tests/test_reader_layout.py`.

- [x] 先写失败测试：目录段落逐行纵向显示，目录标题/页码降为辅助字号；条款标题保持 ID。浏览器核对 CH01-S001 非空白字符 32,648 个，展示前后完全一致。
- [x] `readingHTML` 完成安全 DOM 重建后标记目录与页码，不信任正文样式或脚本。
- [x] `.extracted-block { white-space: normal; }`；原始行模式单独恢复 `pre-wrap`。两种模式始终保留免责声明与原件链接。
- [x] 双栏（约 248px 文件侧栏 + 宽阅读区），术语按需展开；标题 23–28px，正文 16px，行高约1.85；信息与长获取说明折叠。

## 4. 验证与交付

- [x] 分批执行原件、定位、资料库、前端测试；新增显示逻辑 4 项、PDF 嵌入安全 8 项、压缩协商 3 项均完成红绿验证。
- [x] `python -m unittest discover -s tests -v`：240 项全通过（282.101 秒）；JavaScript逐文件 `node --check` 通过。
- [x] Playwright CLI在1440px与390px验证：目录换行、PDF原件、文字切换、搜索（21处匹配）、条款跳转、无缓存原件回退、无水平溢出；截图保存 `output/playwright/`。
- [x] 独立审查无已证实 P1/P2，独立测试94项通过；确认数据文件无变更。旧服务未停止，新版在 5002 启动并实测。
- [x] 确认交付到现有分支 `feat/offline-resource-hall` 及草稿 PR #2，不合并、不替换旧数据；提交与推送结果以 Git 执行结果为准。
- [ ] 新版公网临时网址：启动分享通道被策略拒绝，未绕过；不得将连接旧服务的临时地址视作新版验收地址。

## 额外修复与限制

- 长文本响应按客户端能力启用 gzip；实测长文 JSON 从 292,524 字节降至 68,020 字节。PDF、Range、HEAD、错误响应不压缩；`gzip;q=0` 不压缩。
- Windows CI 原件路径测试统一解析临时目录根路径，保留原件哈希安全断言；真实 Windows 短路径环境20项测试通过。
- 浏览器不支持 PDF 插件或缓存原件随后失效时，采用文字/官方链接手动回退，不声称自动检测 PDF 插件是否成功渲染。
- 专业审核状态、来源正文和哈希保持不变；本次不增加 AI 内容、知识图谱或资料。
