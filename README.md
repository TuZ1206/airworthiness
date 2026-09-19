# 民用航空适航知识图谱与智能问答

本仓库用于复现一个面向国内民用航空适航资料的演示系统。当前只完成两个板块：

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

以下是团队确认清理旧文件后采用的目标结构。当前仓库中的旧版单文件程序和压缩包暂时保留，不要继续在压缩包或千行脚本中增加新内容。

```text
airworthiness/
├─ src/airworthiness/
│  ├─ app.py                 # Flask 启动入口
│  ├─ config.py              # 读取环境变量
│  ├─ web/                   # 页面、路由、静态资源
│  ├─ graph/                 # Neo4j 导入、查询、图谱服务
│  └─ qa/                    # Dify API 调用和问答服务
├─ data/chapters/
│  ├─ ch01/
│  ├─ ch02/
│  ├─ ...
│  └─ ch09/                  # 每章均采用下方“章节提交包”格式
├─ templates/
│  ├─ chapter/               # 章节数据模板
│  └─ crawler/               # 爬虫配置模板
├─ tests/
│  ├─ graph/
│  └─ qa/
├─ docs/                     # 架构、演示和会议文档
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

## 三、从零构建环境

推荐 Windows、Python 3.11、Neo4j 5.x。Dify 可以使用云服务或本地部署，本项目通过 HTTP API 调用，不在仓库中重复实现 RAG。

```powershell
git clone https://github.com/TuZ1206/airworthiness.git
cd airworthiness
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

然后在本机 `.env` 中填写 Neo4j、Dify 和 DeepSeek 配置。`.env` 只保存在个人电脑，不得上传。

当前旧版代码的具体启动方式可能随整理而变化；完成目录迁移后，应把唯一有效的启动命令固定为：

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
├─ review.md             # 专业审核记录
├─ crawler_config.json   # 本章爬虫入口与关键词
└─ documents/
   ├─ CH06-S001.md       # 与 source_id 同名的清洗正文
   └─ ...
```

对应模板位于 [`templates/chapter`](templates/chapter) 和 [`templates/crawler`](templates/crawler)。复制模板后再填写，不要随意增删表头。

### `sources.csv`

```text
source_id,title,document_code,document_status,publish_date,url,sha256,crawled_at,review_status
```

### `nodes.csv`

```text
node_id,chapter_id,label,name,code,summary,source_id,source_locator,priority,review_status
```

### `relations.csv`

```text
relation_id,from_node_id,type,to_node_id,source_id,evidence,review_status
```

统一状态值：

- `pending`：待审核
- `approved`：审核通过
- `rejected`：不采用
- `update_required`：需要修改后再审

`document_status` 使用 `effective`、`abolished`、`unknown`；`priority` 使用 `high`、`medium`、`low`。

编号规则：来源 `CH06-S001`，节点 `CH06-N001`，章内关系 `CH06-R001`，跨章关系 `CROSS-R001`。节点和关系编号一经合并不得重复使用或随意更换。

示例行只展示格式，不代表专业结论；复制后必须根据原文修改并保持 `review_status=pending`，直到专业成员签字确认。

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
- [ ] 示例内容已替换，编号在全仓库中唯一。
- [ ] 专业结论已记录在 `review.md`。
- [ ] 未提交密钥、缓存、大型二进制文件或重复压缩包。

## 十、旧文件处理原则

当前仓库中的 `Web开发.zip`、根目录旧版 Python 文件及其中的重复内容先保留，等待团队共同确认。确认后再执行一次单独的迁移 PR：提取仍有价值的页面和数据，按目标目录拆分；验证新入口可运行后，才删除重复文件、缓存、压缩包和已泄露配置。不要在本次文档提交中删除它们。
