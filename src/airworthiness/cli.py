"""Reproducible catalog build, validation, report and local serving commands."""
import argparse
import json
from pathlib import Path

from . import catalog
from .config import project_root
from .ingest import load_inputs


def markdown_report(report):
    totals = report["totals"]
    lines = ["# 九章资源质量报告", "", f"生成时间：{report['generated_at']}", "", f"来源登记：{totals['sources']} 条；章节：{totals['chapters']}。跨章重复引用保留来源编号，因此该数字不等于独立法规数量。", "", "所有自动采集结果仍需专业复核。提取正文不等于表格、公式和版式已核验完整。", "", "| 章节 | 登记数 | 网页正文 | 提取正文 | 摘录 | 状态信息 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for chapter in report["chapters"]:
        lines.append(f"| {chapter['id']} {chapter['title']} | {chapter['count']} | {chapter['fulltext_count']} | {chapter['extracted_count']} | {chapter['excerpt_count']} | {chapter['metadata_count']} |")
    lines += ["", "## 待补全文", ""]
    for gap in report["gaps"]:
        reason = gap["reason"].replace("\n", " ")
        lines.append(f"- {gap['source_id']} {gap['title']}：{reason} [官方来源]({gap['url']})")
    if not report["gaps"]:
        lines.append("无仅摘要或状态信息条目；正文完整性和专业含义仍需审核。")
    lines += ["", "## 元数据待核事项", ""]
    for issue in report["issues"]:
        lines.append(f"- {issue['source_id']}：{issue['message']}")
    if not report["issues"]:
        lines.append("未发现自动校验可识别的元数据问题。")
    lines += ["", "## 本轮边界", "", "- CH04-S007 的 HB 8605-2021 标题已按政府标准平台修正为《飞机复合材料结构适航符合性验证通用要求》，更新了该摘录的哈希。", "- 原上传 nodes.csv、relations.csv 保留；本轮不重建或审核图谱数据。旧节点中的同类题名问题仍需后续处理。", "- 不改变 review_status，不提供专业批准，不接入 Neo4j、Dify 或模型服务。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="九章适航法规资源大厅")
    parser.add_argument("command", choices=["build", "validate", "report", "serve"])
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, help="report: Markdown 文件；同时输出同名 JSON")
    args = parser.parse_args(argv)
    root = project_root()
    database = args.database or root / ".cache/library.sqlite3"
    if args.command == "serve":
        from .app import main as serve
        serve()
        return 0
    if args.command == "validate":
        _, docs, _, errors, issues = load_inputs(root)
        print(json.dumps({"sources": len(docs), "errors": errors, "issues": issues}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if args.command == "build":
        print(json.dumps(catalog.build_catalog(root, database), ensure_ascii=False, indent=2))
        return 0
    catalog.ensure_catalog(root, database)
    report = catalog.quality(database)
    output = args.output or root / "docs/data-quality-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown_report(report), encoding="utf-8", newline="\n")
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"报告：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
