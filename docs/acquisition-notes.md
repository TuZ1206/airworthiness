# 官方来源离线采集记录

执行日期：2026-10-13。采集与技术核对不代表专业审核、法规效力判断或批准；所有资料仍为 `pending`。

## 实际结果

九章共 189 条来源登记、135 个唯一登记 URL。当前大厅显示：网页正文 9、提取正文 162、整理摘录 0、状态信息 18。171 条可读正文包含跨章引用，不等于独立法规数量，也不表示图表、公式或法律内容已逐字核实。

最初本机对官方来源的下载受 TLS 连接提前关闭与超时影响。后续通过仓库 GitHub Actions 获取官方原始字节，下载产物并逐个校验缓存 URL、原始字节 SHA-256 后导入。没有关闭 TLS 校验，没有修改系统代理、DNS 或凭据。首次尝试的历史记录见 [初次采集](acquisition-initial-attempt.md)。

- 全量成功运行：[38368418797](https://github.com/TuZ1206/airworthiness/actions/runs/38368418797)，取回 242 对原始缓存与元数据文件。
- 定向附件补充：[38374275626](https://github.com/TuZ1206/airworthiness/actions/runs/38374275626)，获取 CCAR-25 独立附录、CCAR-26 及 CCAR-45 PDF。CCAR-45 合并文本未冒充原登记的修改决定。
- 远端官方网页文字作为补充，独立保存工具快照哈希，不冒充原始 HTTP 字节哈希。

## 特殊文件与限制

| 文件 | 本轮处理 | 必须保留的限制 |
| --- | --- | --- |
| CCAR-25-R4 | 官方主文 434 页＋独立附录 82 页，共 516 页；分别提供原件 | 两套页码分开；文字提取不能还原全部图形和公式 |
| AP-21-11R2 | 官方 RAR 唯一 PDF，233 页；RAR/PDF 双哈希 | PDF 物理第188、189页现有文字层存在错误，必须对照原件 |
| AP-21-AA-2010-04R4 | 133 页扫描件本地 OCR | 第133页未取得识别文字，抽查为空白尾页；封面和表格仍有错字 |
| AC-25.1529-1《审定维修要求》 | 21 页扫描件本地 OCR，修正登记题名的展示值 | 第10页概率公式存在指数丢失，不可直接据 OCR 引用数值或公式 |

本地 OCR 使用 Tesseract 和 `chi_sim+eng` 模型；模型、原 PDF 和识别缓存都在忽略目录，不提交 Git。缓存绑定原 PDF、模型、引擎与参数，空页及错误页不会被当作成功完整文字。OCR 为 `extracted`，不是已校对全文。

已导入的两份实际识别产物保留其真实 v1 缓存键和原PDF哈希；未为更新程序版本改写历史记录。当前OCR程序为v2，使用同一不可变字节快照计算哈希和渲染，每页最多45秒、最多三并发，未来重跑不复用v1缓存。原件接口也只发送重新验过哈希的固定字节快照。

剩余 18 条状态信息对应 13 项标准：4 项有明确的采标版权文本限制；其余涉及动态下载入口、gov.cn 范围以外的官方链接目标或未确认详情。不能一概称“不公开”。逐项证据及实际访问结果见 [标准访问核对](standards-access.md) 和 [质量报告](data-quality-report.md)。HB 7736-2004 仍未确认同号同年的官方详情，查询无结果不能证明标准不存在。

## 文件与接入约定

`data/acquired/manifest.json` 是 `source_id -> entry` 映射。来源绑定、正文和原字节采用不同哈希：

- `source_sha256`：当前上传 CSV 记录绑定的原稿哈希。
- `sha256`：生成的 Markdown UTF-8 字节哈希。
- `original_sha256`：实际 HTTP 原件字节哈希；远端工具文字没有原件字节时留空。
- `tool_snapshot_sha256`：真实工具响应的序列化快照哈希，不等于原件哈希。
- `archive_member_sha256`：RAR 内固定 PDF 的哈希，与 RAR 原件哈希分开。
- `landing_url` 保留台账 URL；`url` 为实际取得内容的官方地址。跨 URL 导入逐 ID 绑定当前哈希、文号、日期，并检查原件中的版本引文。

补采正文放在 `data/acquired/documents/`；新补充文件使用内容寻址路径，同一文件可以跨章引用。原上传 CSV 和原稿不被覆盖。元数据修正放在 `data/verification/metadata-findings.json`，保留原值、证据、修正或解释结论及原问题记录。

`report.json` 的 `counts` 表示当前采集 manifest，`unique_url_counts` 表示当前登记 URL 的最佳可用类型；旧的 `requests/results` 是对应采集运行历史，不代表最新失败清单。追加日志 `attempts.jsonl` 同时保留初次失败、重试与补采记录。大厅质量报告是最终合并后的阅读统计。

原始下载、工具快照、PDF 和 OCR 缓存只保存在 `.cache/`。本地原件接口只读取固定缓存路径，校验官方 URL、长度与哈希；不按任意路径读文件，不实时联网，不执行上传文件。其他电脑没有原件缓存时隐藏 PDF 入口，已提交的文字仍能阅读。

## 复现与安全边界

```powershell
.venv/Scripts/python.exe -m airworthiness.acquire --root . --workers 4 --per-host 2
.venv/Scripts/python.exe -m airworthiness.cli validate
.venv/Scripts/python.exe -m airworthiness.cli build
.venv/Scripts/python.exe -m airworthiness.cli report
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

本机网络若仍受限，可在 GitHub 运行 `source-acquisition.yml` 和 `source-supplement.yml` 后获取产物；Git 不包含下载产物。默认复用已验证成功缓存，`--refresh` 才重新请求。普通响应上限 32 MiB；已核对 RAR 成员的固定本地 PDF 上限 256 MiB。没有自动解包任意归档或绕过授权下载。

远端导入使用 `remote_import.import_remote_snapshot(root, snapshot)`，缓存导入使用 `cached_import.import_cached_original(root, url, source_ids, identity_evidence)`；严格输入格式见模块文档。CLI `--import-web-json` 使用同一严格入口，需要显式来源绑定，不自动把旧格式推测为同版本。只接受真实带行号的工具响应，拒绝缺页、冲突、截断、嵌入伪行号和不匹配版本；图像标记保留为缺失提示。

正文按实际结构生成真实条号、页码或自动阅读段落。自动段落仅用于导航；术语文本匹配不等于法规定义核验。最终集成检查见 [验收说明](offline-acceptance.md)。
