from .neo4j_setup import AviationKnowledgeGraph
import json
import sys


def generate_test_data():
    """生成测试数据并执行示例查询"""
    kg = AviationKnowledgeGraph()

    # 首先获取示例查询
    queries = kg.generate_sample_queries()

    results = {}

    print("=" * 60)
    print("适航法规知识图谱查询演示")
    print("=" * 60)

    for query_name, query in queries.items():
        print(f"\n查询: {query_name}")
        print("-" * 40)

        try:
            data = kg.conn.execute_query(query)
            results[query_name] = data

            if data:
                # 格式化输出
                if query_name == "所有章节":
                    for item in data:
                        print(f"第{item['id']}章: {item['title']}")
                        print(f"  描述: {item['description'][:50]}...")

                elif query_name == "章节及其引用的法规":
                    for item in data:
                        print(f"第{item['chapter_id']}章 {item['chapter_title']}")
                        print(f"  引用法规: {item['article_code']} - {item['article_title']}")

                elif query_name == "概念及其关联章节":
                    for item in data:
                        print(f"概念: {item['concept']}")
                        print(f"  描述: {item['description']}")
                        print(f"  相关章节: {', '.join(item['related_chapters'])}")

                elif "复杂查询" in query_name:
                    for item in data:
                        for key, value in item.items():
                            print(f"  {key}: {value}")

                print(f"找到 {len(data)} 条记录")
            else:
                print("无数据")

        except Exception as e:
            print(f"查询出错: {e}")
            results[query_name] = str(e)

    # 保存查询结果到JSON文件
    with open('query_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n查询结果已保存到 query_results.json")

    return results


def interactive_query():
    """交互式查询界面 - 修正版本"""
    kg = AviationKnowledgeGraph()

    # 首先获取查询语句
    all_queries = kg.generate_sample_queries()

    # 创建交互式菜单
    menu_queries = {
        "1": ("所有章节", all_queries.get("所有章节", "")),
        "2": ("章节引用法规", all_queries.get("章节及其引用的法规", "")),
        "3": ("积木式验证", all_queries.get("积木式验证层级", "")),
        "4": ("概念查询", all_queries.get("概念及其关联章节", "")),
        "5": ("合规方法", all_queries.get("条款的合规方法", "")),
        "6": ("完整路径", all_queries.get("复杂查询：从材料到验证的完整路径", "")),
        "7": ("自定义查询", "")
    }

    # 检查查询语句是否为空
    for key, (name, query) in menu_queries.items():
        if not query and key != "7":
            print(f"警告: 查询 '{name}' 的语句为空")

    while True:
        print("\n" + "=" * 60)
        print("适航法规知识图谱查询系统")
        print("=" * 60)
        print("1. 查看所有章节")
        print("2. 查看章节引用的法规")
        print("3. 查看积木式验证层级")
        print("4. 查看概念定义")
        print("5. 查看条款合规方法")
        print("6. 查看完整验证路径")
        print("7. 自定义Cypher查询")
        print("0. 退出")

        choice = input("\n请选择查询选项 (0-7): ").strip()

        if choice == "0":
            print("感谢使用，再见！")
            break

        elif choice == "7":
            # 自定义查询
            print("\n自定义Cypher查询")
            print("-" * 40)
            cypher_query = input("请输入Cypher查询语句: ").strip()
            if not cypher_query:
                print("查询语句不能为空")
                continue

            try:
                results = kg.conn.execute_query(cypher_query)

                if results:
                    print(f"\n查询结果 ({len(results)} 条记录):")
                    for i, result in enumerate(results, 1):
                        print(f"\n记录 {i}:")
                        for key, value in result.items():
                            print(f"  {key}: {value}")
                else:
                    print("无查询结果")
            except Exception as e:
                print(f"查询错误: {e}")

        elif choice in menu_queries:
            query_name, query = menu_queries[choice]

            if not query:
                print(f"错误: 查询语句为空")
                continue

            print(f"\n执行查询: {query_name}")
            print("-" * 40)

            try:
                results = kg.conn.execute_query(query)

                if results:
                    print(f"找到 {len(results)} 条记录:")
                    for i, result in enumerate(results, 1):
                        print(f"\n结果 {i}:")
                        for key, value in result.items():
                            if isinstance(value, list):
                                print(f"  {key}: {', '.join(str(v) for v in value)}")
                            else:
                                print(f"  {key}: {value}")
                else:
                    print("无查询结果")
            except Exception as e:
                print(f"查询错误: {e}")
        else:
            print("无效选项，请重新选择")


def quick_setup():
    """快速设置知识图谱（不依赖generate_sample_queries）"""
    kg = AviationKnowledgeGraph()

    # 定义查询语句
    predefined_queries = kg.generate_sample_queries()

    print("快速设置知识图谱查询系统")
    print("=" * 60)

    # 执行所有查询
    results = {}
    for query_name, query in predefined_queries.items():
        print(f"\n执行查询: {query_name}")
        print("-" * 40)

        try:
            data = kg.conn.execute_query(query)
            results[query_name] = data

            if data:
                print(f"找到 {len(data)} 条记录")
                # 显示前3条结果
                for i, item in enumerate(data[:3], 1):
                    print(f"\n示例结果 {i}:")
                    for key, value in item.items():
                        if isinstance(value, list):
                            print(f"  {key}: {', '.join(str(v) for v in value[:3])}...")
                        elif isinstance(value, str) and len(value) > 50:
                            print(f"  {key}: {value[:50]}...")
                        else:
                            print(f"  {key}: {value}")
                if len(data) > 3:
                    print(f"  ... 还有 {len(data) - 3} 条记录")
            else:
                print("无数据")

        except Exception as e:
            print(f"查询出错: {e}")
            results[query_name] = str(e)

    # 保存结果
    with open('quick_query_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n查询结果已保存到 quick_query_results.json")
    return results


def show_statistics():
    """显示知识图谱统计信息"""
    kg = AviationKnowledgeGraph()

    statistics_queries = {
        "节点统计": """
        MATCH (n)
        RETURN labels(n)[0] as node_type, count(*) as count
        ORDER BY node_type
        """,

        "关系统计": """
        MATCH ()-[r]->()
        RETURN type(r) as relationship_type, count(*) as count
        ORDER BY count DESC
        """,

        "知识图谱概况": """
        MATCH (n)
        RETURN
          count(DISTINCT n) as total_nodes,
          count{()-->()} as total_relationships,
          count(DISTINCT labels(n)[0]) as node_types,
          count{()-[r]->()} as relationship_count
        """
    }

    print("知识图谱统计信息")
    print("=" * 60)

    for stat_name, query in statistics_queries.items():
        print(f"\n{stat_name}:")
        print("-" * 40)

        try:
            results = kg.conn.execute_query(query)
            for result in results:
                for key, value in result.items():
                    print(f"  {key}: {value}")
        except Exception as e:
            print(f"  查询失败: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "test":
            generate_test_data()
        elif command == "interactive":
            interactive_query()
        elif command == "quick":
            quick_setup()
        elif command == "stats":
            show_statistics()
        elif command == "all":
            print("执行完整测试流程...")
            quick_setup()
            show_statistics()
            interactive_query()
        else:
            print(f"未知命令: {command}")
            print("可用命令: test, interactive, quick, stats, all")
    else:
        # 默认运行交互式查询
        print("未指定命令，运行交互式查询模式")
        interactive_query()
