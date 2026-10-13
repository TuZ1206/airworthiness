# 官方来源离线采集记录

执行日期：2026-10-13。仅机械提取原文，采集成功不代表专业审核、法规效力判定或批准。

## 本次实际结果

- 全量执行覆盖 189 条台账记录、135 个唯一来源 URL。
- 加上现有文档指明的官方 PDF 附件，共请求 228 个不同官方 URL，产生 230 次实际网络尝试。每主机最多 2 个并发，请求启动间隔至少 0.4 秒。
- 本机下载未成功：228 次 TLS 握手提前关闭，另有连接超时、读取超时各 1 次；两个超时已按上限重试。没有关闭 TLS 验证，没有把旧文档或模拟文本作为本次抓取成果。
- 有限网络诊断确认 Python、curl、Node、Edge 和官方 DNS 地址直连均无法从本机取得目标内容。未改动系统代理、DNS 或凭据。
- 远端 web 工具取得《中华人民共和国民用航空器适航管理条例》的 HTML 文字，来源 URL 与 CH01-S002 完全一致。机械选取工具返回的第 75—143 行，保存第一条至第二十九条；没有改写正文。
- 最终 manifest：`fulltext=0`、`extracted=1`、`metadata=0`、`failed=188`；对应唯一来源 URL：`extracted=1`、`failed=134`。另有 3 次有限的远端失败探测，分别为民用航空法读取超时两次、政府网无人机条例页面 403 一次。
- 无原始 PDF 成功下载，因此本次没有可供视觉对照的官方 PDF。PDF 分页与空文字页处理已用本地生成的测试 PDF 验证；不能把这些测试视为对实际官方 PDF 的核验。

## 文件与接入约定

`data/acquired/manifest.json` 是 `source_id -> entry` 直接映射。`path` 位于 `data/acquired/documents/`，使用实际取得的规范化官方 URL 的 SHA-256 命名，同一 URL 共用一个正文路径。

- `sha256`：生成的 Markdown 文件 UTF-8 字节哈希，供离线目录验证。
- `original_sha256`：经 HTTP 下载的原始文件字节哈希。远端工具只提供处理后的 HTML 文字，不能取得原始 HTML 字节，因此 CH01-S002 此字段明确留空，另以 `tool_snapshot_sha256` 记录工具快照哈希；不能将二者混淆。
- `url`：成功取得正文的实际官方地址；失败项保留所尝试的来源地址，不能解释成下载成功。`landing_url` 保留该条台账的 URL。
- `method=web-tool-html-text`：仅表示远端工具返回的 HTML 文字，固定标为 `extracted`、`review_status=pending`。原始 HTML、完整重定向链、图表及页面完整性未核验，不声称 `fulltext`。
- `method=pymupdf-page-text`：只用于真实 PDF 字节的逐页提取，包含 `## 第 N 页`；任何空文字页都会明确列出，所有 PDF 提取均待核验。
- `source_sha256`：采集读取 CSV 时的原记录哈希；不是本次下载的原始字节哈希。

`report.json` 保留全量请求和来源结果，`counts` 表示当前 manifest；`unique_url_counts` 是首次本机全量采集的结果（135 个失败），远端补采另记在 `remote_imports`。`attempts.jsonl` 为追加式逐次尝试记录，保留本机失败、远端成功、远端失败及运行编号。网页成功但附件失败时，manifest 同时保留网页、附件错误和尝试列表。

原始下载和远端工具快照仅保存至 `.cache/acquisition/`，缓存目录自带忽略文件，仓库的父任务也已忽略 `.cache`。缓存读取重新验证官方 URL 和原始字节哈希。PDF 二进制不会写入 `data/acquired`。

HTML 提取限制在识别出的正文容器；标准平台页面固定为 `metadata`。通知中只引用单个条款不会被认作完整正文。只选择首个可提取的 PDF 附件，多个附件的未合并情况会记录；不会声称多附件已全部取得。HTML 图像、跨单元格表格结构和分页仍需核验。

重跑保留有有效本地哈希且质量更好的已有采集正文；重复来源或新的 URL 别名也不能覆盖该正文。原章节 CSV 和文档由父任务维护，本采集器不修改。CH04-S007 的父任务标题与哈希修正未撤销。

## 复现

从仓库根目录运行：

```powershell
.venv/Scripts/python.exe src/airworthiness/acquire.py --root . --workers 4 --per-host 2
.venv/Scripts/python.exe -m unittest tests.test_acquire tests.test_chapter_data_format -q
```

默认复用已验证的成功缓存；`--refresh` 强制重新请求，仍保留更好的已有正文。连接/读取超时为 3.5/9 秒，最多 1 次重试、5 次重定向、32 MiB 响应、8 个 PDF 候选、1500 页 PDF 提取上限；不对 TLS 错误反复重试。`--proxy` 仅接受明确指定且无凭据的代理 URL，不读取环境认证、`.netrc` 或其他凭据文件。

`--import-web-json` 从标准输入接收已取得的真实远端 HTML 工具响应，不发网络请求。每条输入包括 `url`、`responses`、`line_start`、`line_end`、`captured_at`；逐个核验官方来源、HTML 类型及所选行的连续性，拒绝截断、冲突、导航标记及 PDF 响应。此次完整工具快照保存在忽略的 `.cache/acquisition/<canonical-url-hash>.web.json`，可用于复验；不包含该快照时，无法在纯离线环境重新取得官网原文。

网络层已拆到 `src/airworthiness/acquire_http.py`；`acquire.py` 保留 `Fetcher`、`AcquisitionError`、URL 验证等既有导出，父任务的 manifest 接入无需改变。

## 验证结果

29 项采集测试及 6 项原章节格式/哈希校验通过。已检查 189 个 manifest 键、官方 URL、正文路径及 SHA-256、234 条日志、全部 135 个来源 URL 的请求覆盖，以及条例第一条至第二十九条的原样文本。两个实现模块分别为 433、253 行，测试文件 359 行，均低于 500 行。

原始 PDF 下载和视觉核验仍受网络阻断，不作成功声明。资源大厅的最终集成验证见 `offline-acceptance.md`；采集单项测试不替代整体应用验收。
