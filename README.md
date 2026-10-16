# 民用航空适航法规资源大厅

## GitHub Pages 在线验收版

发布地址由仓库 Settings → Pages 提供；目标地址为 <https://tuz1206.github.io/airworthiness/>。只有 `Publish resource hall to GitHub Pages` 工作流成功并完成访问验证后才视为上线，不能把分支推送成功当成部署完成。

- 在线版复用九章正文、目录、术语和质量报告，不需要访问者安装 Python，也不依赖分享电脑开机。它是构建时的只读快照，不代表法规现行有效或专业审核通过。
- 浏览器执行标题、文号和正文的字面关键词检索，支持章节/效力/收录类型筛选与分页。结果按来源编号排列，与本机 SQLite 的相关性排序不同；首次有关键词搜索会下载压缩的章节索引，旧浏览器可回退普通 JSON。
- 自动发布不把本机 `.cache`、数据库、密钥或原始二进制附件提交到 Git。Pages 构建时只下载并校验台账中有原件 SHA-256 的现行 CCAR、AP、AC 官方 PDF；校验成功的副本只进入临时站点产物供页内阅读。标准全文、失效文件、仅有状态页及哈希不符的文件不进入产物，页面保留政府官网原件入口。图表、公式与扫描版式以原件为准，不能把提取文字当作完整原件。
- Pages 的 Source 使用 **GitHub Actions**，`github-pages` 环境允许发布分支 **feat/offline-resource-hall**。推送该分支会测试、导出并发布；不自动合并草稿 PR，不修改 `main`。如以后更换发布分支，需要同时更新工作流触发分支与环境允许列表。

本机复现静态站（输出目录必须为空或不存在）：

```powershell
.\.venv\Scripts\python.exe -m airworthiness.static_export --root . --output output/pages/airworthiness --base-path /airworthiness
.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory output/pages
```

打开 <http://127.0.0.1:8000/airworthiness/>。需要复现在线 PDF 阅读时，先运行 `python -m airworthiness.public_pdfs --root .`，再给静态导出命令添加 `--include-originals`；只会纳入已校验且符合发布范围的官方 PDF。下载缓存和 PDF 均不提交到 Git。静态站导出是生成副本，不修改原始正文、哈希或审核状态。

## 当前可运行版本：九章离线资源大厅

本轮重建提供九章资料浏览、多文档本地阅读、中文全文检索、来源追溯、资料质量报告和章节末尾的待审图谱预览。图谱直接读取每章 `nodes.csv`、`relations.csv`，以导读专题作为浏览分组；专题树枝不是法规上下位关系，实际关联仅来自关系表。**暂不启用正式 Neo4j、Dify 或 AI 问答**；专业审核与数据规则继续保留。旧版硬编码页面和程序已在本分支移除，可通过 Git 历史恢复。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m airworthiness.app
```

打开 <http://127.0.0.1:5000>。也可运行 `powershell -ExecutionPolicy Bypass -File .\start.ps1`。无需配置密钥或 `.env`；首次安装依赖需要联网，之后已保存内容可离线浏览。

- 一份文件独立保存；同一章节内切换文件无需跳官网。官方链接用于额外核验。
- PDF 资料优先嵌入已校验的原件；没有可发布副本时默认显示官方 PDF 阅读入口，不把被官网屏蔽的远程嵌入伪装成可用预览。可切换“文字检索”；搜索结果或条款定位仍直接打开文字位置，以保留精确定位。手机或浏览器无法内嵌已校验 PDF 时，使用“新窗口打开原件”或“官方来源”。HTML 正文及只有标准状态信息的记录不伪装成 PDF。
- 提取文字采用自动换行，可手动恢复提取换行，但不承诺还原表格、公式和 OCR；网页目录和分项逐行显示。排版优化只作用于界面，不修改原始正文和哈希。
- 来源记录数包含跨章重复引用，不等于独立法规数。
- **网页正文**：从已识别的官方正文区域提取；**提取正文**：附件机械提取，表格、公式和完整性待校对；**摘录／状态信息**：未获得全文，不冒充原文。
- 上传资料位于 `data/chapters/`，补抓正文和获取记录位于 `data/acquired/`，SQLite 检索索引位于被忽略的 `.cache/`。资料变化后重启应用自动重建索引。
- 来源审核状态不会因自动采集成功而改变；页面仍显示待专业审核。

2026-10-13 本轮补齐后：189 条来源登记中，9 条为网页正文、162 条为提取正文、18 条为标准状态信息，整理摘录为 0。171 条可读正文包含跨章引用，不等于 171 份独立、完整或已审核的法规。剩余 18 条对应 13 项标准，获取限制逐项见 [标准访问核对](docs/standards-access.md)。

- CCAR-25-R4 主文 434 页和独立附录 82 页分别保留分页，并提供两个本地 PDF 对照入口。
- AP-21-11R2 从官方 RAR 内 PDF 提取 233 页；RAR 和包内 PDF 各自校验哈希。
- 两份扫描 PDF 已完成本地 OCR，仍标“识别文字，待校对”；公式指数、表格和错字必须对照原件。
- 132 个术语中 68 个有原文文本匹配定位，64 个仅定位到来源文件；状态说明和整理摘录不作为原文匹配依据。这些匹配不是定义审核，也不冒充核实后的条款依据。
- 元数据采用独立证据覆盖层，保留上传原值和已处理提示。26 项原提示中 25 项已修正或解释，HB 7736-2004 的日期与官方详情仍待核对。

本地 PDF 按钮只在对应缓存原件及哈希有效时出现；Git 仓库只保存提取文字和追溯信息。其他电脑克隆后能离线阅读文字，但需要单独获取原件缓存，不能把“仓库包含正文”理解为“仓库包含 PDF”。

### 验证与报告

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m airworthiness.cli validate
.\.venv\Scripts\python.exe -m airworthiness.cli build
.\.venv\Scripts\python.exe -m airworthiness.cli report
```

页面 `/quality` 显示同一份质量统计；生成报告位于 `docs/data-quality-report.md`。详细操作见 [验收说明](docs/offline-acceptance.md)。重新获取官方资料使用 `python -m airworthiness.acquire --root .`，其输出不会覆盖上传原稿，下载失败会明确记录。原始二进制附件留在本地缓存，不提交 Git。

当前实现分工：`ingest.py` 读取和校验资料，`catalog.py` 构建和查询 SQLite，`reading.py` 安全渲染正文，`app.py` 提供本机 API，`acquire.py` 获取官方资料，`cli.py` 提供构建和报告命令。

---

## 后续系统目标与资料规则

本仓库的后续目标是面向国内民用航空适航资料完成两个板块：

1. **知识图谱**：把九章资料整理为可审查的节点和关系，审核后导入 Neo4j。
2. **AI 问答**：把审核通过的原文资料交给 Dify 建立知识库，由 DeepSeek 生成带来源的回答。

“提交材料合规检查”等第三板块目前不做。专业结论由专业成员确认，技术成员只负责采集、整理、导入、检索和界面实现。

## 一、工作流程

```text
gov.cn / *.gov.cn 官方页面
        │
        ├─ 资料原文 → 专业审核 → Dify 知识库 → DeepSeek → Flask 问答页面
        │
        └─ 节点/关系表 → 专业审核 → Neo4j → 图谱查询与展示
```

每章可以独立整理，九章完成后再统一检查编号、重名节点和跨章关系。未经专业审核的数据不得导入正式 Neo4j 图谱或正式 Dify 知识库。

## 二、建议目录

以下为包含后续图谱与问答模块的目标结构；当前离线实现见本文开头，不要恢复旧版硬编码程序或在压缩包中开发。

```text
airworthiness/
├─ src/airworthiness/
│  ├─ __init__.py
│  ├─ app.py                 # Flask 启动入口
│  ├─ config.py              # 读取 .env 配置
│  ├─ graph/
│  │  ├─ __init__.py
│  │  ├─ neo4j_setup.py      # Neo4j 连接与知识图谱构建
│  │  └─ data_generator.py   # 测试数据生成与示例查询
│  ├─ web/
│  │  ├─ __init__.py
│  │  ├─ templates/          # Flask HTML 模板
│  │  ├─ concept/            # 概念词条页
│  │  └─ image_file/         # 法规原文页
│  └─ qa/
│     └─ __init__.py         # 预留 Dify 问答服务
├─ data/chapters/
│  ├─ guides.json            # 九章阅读导读与专题导航配置，不含法规原文
│  ├─ ch01/ ... ch09/        # 九章数据（sources/nodes/relations/glossary 等）
├─ templates/
│  ├─ chapter/               # 章节数据模板
│  └─ crawler/               # 爬虫配置模板
├─ tests/
│  └─ __init__.py
├─ docs/                     # 架构、部署、会议文档
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

## 三、后续图谱与问答服务环境

离线资源大厅只需要 Python 3.11 或以上（SQLite 需支持 FTS5 trigram，官方 Python 发行版通常已包含）。后续图谱采用 Neo4j 5.x；Dify 可以使用云服务或本地部署，通过 HTTP API 调用，不在仓库中重复实现 RAG。

```powershell
git clone https://github.com/TuZ1206/airworthiness.git
cd airworthiness
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

当前离线版本无需 `.env`。后续恢复服务接入时再添加 Neo4j、Dify 配置；真实密钥只保存在本机，不能上传。

`pip install -e .` 会按 `pyproject.toml` 安装依赖，并以可编辑方式注册 `airworthiness` 包（源码在 `src/` 下）。启动命令固定为：

```powershell
python -m airworthiness.app
```

## 四、九章资料来源规则

- 只收录中国政府网站，网址主机名必须等于 `gov.cn` 或以 `.gov.cn` 结尾。
- 不使用国际组织、商业网站、博客、百科或二次转载作为正式依据。
- 保存标题、文号、发布日期、有效状态、原始网址、抓取时间和 SHA-256。
- 网页正文转换为 UTF-8 Markdown；不要把大体积 PDF、Word 或网页快照直接提交到 Git。
- 一个文件对应一份正式文件，正文不得自行改写；清洗只删除导航、广告和页脚等非正文内容。
- 失效或废止文件可以留作追溯，但 `document_status` 必须标明，不能进入正式 Dify 知识库。
- 链接、条款和专业含义必须经过人工复核。爬虫结果不是专业结论。

域名校验示例：

```python
from urllib.parse import urlparse

host = (urlparse(url).hostname or "").lower().rstrip(".")
allowed = host == "gov.cn" or host.endswith(".gov.cn")
```

## 五、每章必须提交的文件

每章放在 `data/chapters/ch01` 至 `ch09` 中，目录和文件名必须一致：

```text
ch06/
├─ README.md             # 本章范围、状态和待确认事项
├─ sources.csv           # 官方来源清单
├─ nodes.csv             # 知识图谱节点
├─ relations.csv         # 知识图谱关系
├─ glossary.csv          # 右侧名词索引（概念、定义、跳转）
├─ review.md             # 专业审核记录
├─ crawler_config.json   # 本章爬虫入口与关键词
└─ documents/
   ├─ CH06-S001.md       # 与 source_id 同名的清洗正文
   └─ ...
```

对应模板位于 [`templates/chapter`](templates/chapter) 和 [`templates/crawler`](templates/crawler)。复制模板后再填写，不要随意增删表头。

九章阅读器的专题路径维护在 [`data/chapters/guides.json`](data/chapters/guides.json)。每个专题只写原创导语并引用本章已有 `source_id`；只有可阅读正文中确实出现的条款才能填写 `locator`。这份导航配置不改变各章 CSV 表头、法规原文或专业审核状态，状态页不得用来证明具体技术条款。

### `sources.csv`

```text
source_id,title,document_code,document_status,publish_date,url,sha256,crawled_at,review_status
```

### `nodes.csv`

```text
node_id,chapter_id,label,name,code,summary,display_type,source_id,source_locator,priority,review_status
```

### `relations.csv`

```text
relation_id,from_node_id,type,to_node_id,source_id,evidence,review_status
```

### `glossary.csv`

```text
term_id,term,aliases,definition,group,has_page,anchor_or_url,related_node_id,source_id,review_status
```

`glossary.csv` 是右侧名词索引表，与知识图谱节点分离：`term` 是名词，`definition` 是一句话解释，`group` 决定右侧栏分组，`has_page` 表示是否已有独立词条页，`anchor_or_url` 填正文锚点（如 `#s2-1`）或词条链接（如 `/concept/xxx`）。`related_node_id` 可选，用于把名词索引关联到 `nodes.csv` 中的图谱节点。

统一状态值：

- `pending`：待审核
- `approved`：审核通过
- `rejected`：不采用
- `update_required`：需要修改后再审

`document_status` 使用 `effective`、`abolished`、`unknown`；`priority` 使用 `high`、`medium`、`low`。

`display_type` 用于前端图谱配色和分组，取值 `law`（法律）、`norm`（规范性文件）、`concept`（概念）、`process`（过程）、`material`（材料）。

编号规则：来源 `CH06-S001`，节点 `CH06-N001`，名词 `CH06-T001`，章内关系 `CH06-R001`，跨章关系 `CROSS-R001`。编号一经合并不得重复使用或随意更换。

示例行只展示格式，不代表专业结论；复制后必须根据原文修改并保持 `review_status=pending`，直到专业成员签字确认。

### 前端展示数据对应

每章详情页采用“正文 + 左侧目录 + 右侧名词索引 + 底部图谱”的布局，由以下数据渲染：

- 正文：`documents/*.md`，标题层级 `##` / `###` / `####` 自动生成左侧目录和锚点。
- 右侧名词索引：`glossary.csv`，提供名词、定义、分组、是否词条和跳转链接。
- 图谱节点：`nodes.csv`，用 `display_type` 分色，`label` 保持 Neo4j 语义标签。
- 图谱关系：`relations.csv`，边带 `type` 作为关系标签。

目录和名词跳转都依赖正文标题锚点，因此正文标题不能随意改写；名词索引中的 `anchor_or_url` 必须能指向真实存在的正文锚点或词条页。

## 六、Neo4j 与 Dify 的数据边界

### Neo4j

- 只导入 `review_status=approved` 的节点和关系。
- 导入前检查节点编号唯一、关系两端节点存在、来源编号有效。
- 各章先独立导入测试库，九章合并后再建立跨章关系。
- 图谱标签和关系类型应复用已有词汇，新增类型需在 PR 中说明。

### Dify

- 只上传 `review_status=approved` 且 `document_status=effective` 的正文。
- 每个知识库文档保留 `source_id`、标题、文号和原始 URL，回答必须能回溯来源。
- Dify 负责分段、向量检索和上下文召回；DeepSeek 负责依据召回内容组织答案。
- 如果资料中没有答案，应明确回复“当前知识库未找到依据”，不得编造条款。

## 七、代码和文件规范

- 一个 Python 文件只承担一种职责；建议不超过 300 行，原则上不得超过 500 行。
- 不把节点、关系或大段法规正文硬编码进 Python；数据使用 CSV、JSON、Markdown。
- 不提交 `.env`、密码、API Key、数据库备份、缓存、虚拟环境或 IDE 配置。
- 不提交 ZIP 作为源代码交付；文件必须解压、分类后提交。
- 函数和变量用英文，面向用户的文字与文档可用中文。
- 所有文本使用 UTF-8，CSV 使用英文逗号，时间使用 ISO 8601。
- 新功能至少提供一个最小测试或可重复验证命令。

仓库历史中若曾上传真实密钥，应立即轮换密钥；仅删除当前 `.env` 不能清除 Git 历史中的密钥。

## 八、分支与提交规则

需要建立分支。`main` 只保存可运行、已审核的版本，不直接在 `main` 上开发。

分支示例：

```text
chapter/ch06-quality-supply-chain
feat/neo4j-loader
feat/dify-qa
feat/frontend
fix/source-parser
docs/repository-guidelines
```

规则：

1. 一项任务使用一个短期分支。
2. 提交前先同步 `main`，解决冲突后再发起 Pull Request。
3. PR 至少由一名队友检查；专业数据的 PR 必须由专业成员确认。
4. 不把九章内容一次性混在同一个 PR 中。
5. 提交信息使用 `类型: 内容`，例如 `data: add chapter 6 reviewed nodes`、`feat: add neo4j csv importer`。

## 九、章节 PR 检查清单

- [ ] 文件位于正确章节目录，文件名与模板一致。
- [ ] 所有正式 URL 均为 `gov.cn` 或 `.gov.cn` 域名。
- [ ] `sources.csv` 中的 URL、文号、状态和哈希完整。
- [ ] 每个节点能追溯到 `source_id` 和具体条款/段落。
- [ ] 每条关系的起点、终点和来源均存在。
- [ ] 每个名词的 `anchor_or_url` 能指向真实存在的正文锚点或词条页。
- [ ] 示例内容已替换，编号在全仓库中唯一。
- [ ] 专业结论已记录在 `review.md`。
- [ ] 未提交密钥、缓存、大型二进制文件或重复压缩包。

## 十、旧文件处理结果

旧版本曾完成文件归类，本轮进一步移除了旧应用实现：

- `src/airworthiness/app.py` 已替换为离线资源大厅，不包含硬编码法规、模型调用或 Neo4j 启动依赖。
- 旧图谱脚本、旧问答页面、旧章节详情和静态法规页面已移除；需要时从 Git 历史查看，不作为当前运行内容。
- 九章 `nodes.csv` 和 `relations.csv` 驱动页面底部的交互式待审图谱；仅供浏览与核对，不执行正式 Neo4j 导入。
- 含密钥的 `.env` 已从仓库删除；该文件曾进入 Git 历史，相关密钥应尽快轮换。

后续不要再提交 ZIP、缓存（`__pycache__`、`.pytest_cache`）或 `.env`。
