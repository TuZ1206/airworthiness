# 官方正文补全与可追溯定位实施计划

> For agentic workers: use executing-plans for the main integration and dispatching-parallel-agents for the independent metadata and locator tasks. 用户已授权继续执行，最终审核不在本轮范围。

**Goal:** 尽可能补齐官方可公开取得的正文，纠正有证据的元数据错误，提供真实条款/原文匹配定位，并逐项记录无法取得的资料。

**Architecture:** 继续使用当前重建分支和 SQLite；原上传文件保留，补采及核验结果独立记录。只依据来源明确、内容完整的实际工具/HTTP响应导入正文，不能用搜索摘要拼造法规。正文来源、页面/行号、哈希与采集方式分开保存，最终审核状态保持 pending。

**Tech Stack:** Python、Flask、SQLite、PyMuPDF、官方网页/附件、现有原生 JS 前端。

## 任务 1：诊断并恢复官方采集（主任务）

- [x] 对一份 CAAC 页面和标准平台页面作有限的直连/已有系统代理探测，不改系统配置、不关闭 TLS 校验。
- [x] 若本机仍不可达，使用远端官方页面阅读，获取真实附件 URL；优先影响多章的共有法规。
- [x] 为需要的工具导入路径先写失败测试，覆盖缺页、重复行冲突、非官方域名、来源绑定、截断文本。
- [x] 保留原始工具响应到忽略缓存，机械提取正文到 data/acquired，更新 manifest 及追加日志；不得将元数据页算全文。

## 任务 2：元数据证据核验（独立并行）

- [x] 核对质量报告的 26 项提示，输出 data/verification/metadata-findings.json 和 docs/metadata-verification.md。
- [x] 每项记录官方证据 URL、核验时间、旧值、可证实的新值与结论；通知题名与正文题名、发布日与网站更新日分开。
- [x] 主任务只应用证据充分的修正并保持来源绑定一致；不能确认的继续保留具体原因。

## 任务 3：条款和文本定位（独立并行）

- [x] tests/test_locators.py 先断言真实第X条/章生成稳定锚点，数字量值不作为条款，重复目录编号不冒充正文位置。
- [x] reading.py 保持原文字句；locators.py 只返回正文中实际存在的证据位置，区分 clause/text_match/source_only。
- [x] 主任务接入 ingest/catalog 和术语来源链接；新增接口集成测试，再检查浏览器跳转。

## 任务 4：整体验证与交付

- [x] 运行 `.venv/Scripts/python.exe -m unittest discover -s tests -v`、`python -m airworthiness.cli validate`、`python -m airworthiness.cli report`。
- [x] 校验所有来源哈希、保留的原节点关系表、获取证据与有效状态，记录全文/摘录/状态的最终实际统计。
- [x] 重启本地服务，浏览器验证检索、源文件切换、真实条款与术语定位、质量报告；代码审查后提交至现有草稿 PR，不合并主分支。
- [x] 按逐项证据交付未解决清单：不公开/需授权、链接失效、网络不可达、原文提取无法可靠恢复；不把这些归为“等用户审核”。
