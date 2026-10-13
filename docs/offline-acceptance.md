# 今晚验收：九章离线资源大厅

本轮范围：本机阅读、中文关键词检索、资料来源与缺口报告。无需 Neo4j、API Key 或模型服务。

## 启动

在仓库目录运行 `powershell -ExecutionPolicy Bypass -File .\start.ps1`，打开 <http://127.0.0.1:5000>。首次运行需要联网安装 Python 依赖；安装与索引完成后可离线浏览已保存资料。官方原文跳转、重新采集需要联网。

也可以手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m airworthiness.cli build
.\.venv\Scripts\python.exe -m airworthiness.app
```

## 验收操作

1. 首页显示九章和 189 条来源登记；重复引用不等于独立法规。
2. 搜索“复合材料”“适航”和“CCAR-25”，查看命中片段；组合章节与有效状态筛选。
3. 进入任意章节，在同一阅读区切换文件；点击正文目录定位，返回此前文档验证阅读位置。
4. 查看名词解释及其依据文档。名词定义仍为待专业审核的整理内容，不能冒充原文。
5. 区分网页正文、提取正文、摘录与状态信息；废止、未知、待审标识不能被隐藏。
6. 打开“资料质量”页面，核对各章正文情况、缺口和元数据问题。
7. 浏览器缩窄到手机宽度，仍能选择章节、切换文件、搜索和返回。

## 可重复验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m airworthiness.cli validate
.\.venv\Scripts\python.exe -m airworthiness.cli report
```

质量报告输出到 `docs/data-quality-report.md` 和 `.json`。资料更新后重启应用会根据输入变化重建索引；服务运行期间手动重建后刷新页面即可。

## 数据边界

- 原提交仍位于 `data/chapters/`。补抓正文位于 `data/acquired/`，以 manifest 记录实际获取链接、时间及哈希；原始 PDF 只进入本地缓存。
- 网页正文和 PDF 提取文本均待复核。没有取得正文时保留原摘录或状态信息，并展示实际获取失败原因。
- 自动校验不改变专业审核状态。所有资料仍需专业成员确认有效性、适用性、条款与完整性。
- 旧应用在本分支替换，Git 历史可恢复；原节点、关系数据保留，今晚不启用图谱。

## 本机验证记录（2026-10-13）

- Windows、Python 3.13.9；新建 `.venv` 后安装成功，`pip check` 无依赖冲突。
- 最终全套 52 项自动测试通过；前端 JavaScript 语法检查与 `git diff --check` 通过。原有 `nodes.csv`、`relations.csv` 与资料分支逐文件比较无变更。
- 九章页面、九章资料接口、每章代表文档以及全部前端静态资源返回成功。
- 浏览器实际验证中文检索、章节筛选、文件切换、目录跳转，以及切换后恢复原阅读位置；390 像素窄屏无横向溢出，章节和术语面板可展开。
- 189 条来源登记中，109 条可阅读提取正文（含跨章复用），61 条为摘录，19 条为状态信息。所有内容仍待专业审核；不等于 109 份独立或已校对完整的法规。
- 全量官方补抓受本机网络阻断；远端官方页面补回 1 份条例正文。详细记录见 [采集说明](acquisition-notes.md)，其余缺口见 [质量报告](data-quality-report.md)。
- 词条旧锚点暂映射到真实存在的来源文件；保留原锚点值供后续精确条款定位，不宣称已经完成所有逐条定位。
- 质量检查列出 26 项待复核问题，包括同一来源文号差异、同一文号的日期/题名差异和缺少日期；这些提示不自动判定哪一版本正确。正文的采集时间、来源编号和已记录的哈希可在阅读页展开查看。
- 当前 CI 配置包含 Windows/Linux 的离线测试，不运行联网爬取；本机测试通过不能代替远端 CI 的执行结果。
