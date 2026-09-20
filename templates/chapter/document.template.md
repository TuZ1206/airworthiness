---
source_id: CHXX-S001
title: 正式文件标题
document_code: 文件文号
document_status: effective
publish_date: YYYY-MM-DD
url: https://example.gov.cn/path/to/document.html
crawled_at: YYYY-MM-DDTHH:MM:SS+08:00
review_status: pending
---

# 正式文件标题

正文按标准 Markdown 标题层级组织，前端目录由标题自动生成：

- `##`：章内小节（生成左侧目录一级项）
- `###`：次级标题（生成左侧目录二级项）
- `####`：更细的子节

标题文本同时作为目录条目和锚点；`glossary.csv` 中的 `anchor_or_url` 必须能指向某个 `###` 或 `####` 标题对应的锚点。

正文不得自行概括或改写原文；删除导航、广告、页脚等非正文内容即可。