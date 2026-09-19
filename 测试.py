# neo4j_setup.py (整合第一章重构内容的web兼容版本)
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("aviation-kg")


class Neo4jConnection:
    """
    兼容你的 Flask 代码：
    - 保留 execute_query(query, parameters=None) -> List[dict]
    同时提供 execute_write / execute_read 以便结构化调用
    """

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")

        if not password:
            raise ValueError("环境变量 NEO4J_PASSWORD 未设置，请在 .env 中配置。")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info("Neo4j driver initialized (uri=%s, user=%s)", uri, user)

    def close(self) -> None:
        self.driver.close()
        logger.info("Neo4j connection closed.")

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """兼容旧代码的统一入口（读写都能跑，但建议写操作用 execute_write）"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_write(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            with self.driver.session() as session:
                return session.execute_write(lambda tx: tx.run(query, parameters or {}).data())
        except Neo4jError as e:
            logger.error("Neo4j write error: %s", e)
            raise

    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            with self.driver.session() as session:
                return session.execute_read(lambda tx: tx.run(query, parameters or {}).data())
        except Neo4jError as e:
            logger.error("Neo4j read error: %s", e)
            raise


# ----------------------------
# Data (Ch1–Ch9) - 第一章使用重构后的内容
# ----------------------------
CHAPTERS = [
    # 第一章使用重构后的层级化结构
    {"id": 1, "title": "适航法规体系与复合材料结构概论",
     "description": "适航法规层级结构与复合材料结构适航规范体系"},

    # 第2-9章保持不变
    {"id": 2, "title": "复合材料结构适航验证总体框架",
     "description": "合规方法，验证证据链，取证与审查流程，知识图谱的法规映射方式"},
    {"id": 3, "title": "材料性能与材料级验证",
     "description": "基本力学性能，环境影响，材料数据库与B值设计允许值，材料等同验证基础"},
    {"id": 4, "title": "制造工艺与工艺验证",
     "description": "成型工艺控制，工艺窗口与一致性，工艺鉴定，缺陷与无损检测要求"},
    {"id": 5, "title": "等同验证与变更管理",
     "description": "材料等同，工艺等同，供应商变更适航影响，配置控制与适航批准"},
    {"id": 6, "title": "质量体系与供应链适航监管",
     "description": "供应商质量管理，生产批准，质量控制与审查要点，数据追溯与合规记录"},
    {"id": 7, "title": "积木式验证方法",
     "description": "Coupon → Element → Subcomponent → Full-scale，试验计划与审查关注点"},
    {"id": 8, "title": "疲劳与损伤容限要求",
     "description": "冲击损伤评估，残余强度与增长，修理容限，持续适航要求"},
    {"id": 9, "title": "结构设计审查与适航符合性分析",
     "description": "连接与接头设计，分析方法与仿真验证，结构审查典型问题"},
]

# 第一章使用重构后的ARTICLES定义
ARTICLES = [
    # ---------------------------
    # 法律层 (第一章重构内容)
    # ---------------------------
    {
        "code": "AVIATION_LAW",
        "title": "《中华人民共和国民用航空法》",
        "content": "我国民用航空活动及适航管理的最高法律依据",
        "authority": "全国人大常委会"
    },

    # ---------------------------
    # 行政法规层 (第一章重构内容)
    # ---------------------------
    {
        "code": "AIRWORTHINESS_REGULATION",
        "title": "《民用航空器适航管理条例》",
        "content": "国务院颁布的民用航空器适航管理行政法规",
        "authority": "国务院"
    },

    # ---------------------------
    # 规章层（CCAR）(第一章重构内容)
    # ---------------------------
    {
        "code": "CCAR-21",
        "title": "民用航空产品和零部件合格审定规定",
        "content": "规定型号合格证、生产许可证等管理要求",
        "authority": "CAAC"
    },
    {
        "code": "CCAR-25-R4",
        "title": "运输类飞机适航标准",
        "content": "运输类飞机结构、系统与环境适航标准",
        "authority": "CAAC"
    },

    # CCAR-25 条款（挂在 R4 下）(第一章重构内容)
    {
        "code": "CCAR-25.301",
        "title": "载荷",
        "content": "结构必须承受限制载荷而不产生有害永久变形",
        "authority": "CAAC"
    },
    {
        "code": "CCAR-25.305",
        "title": "强度和变形",
        "content": "结构必须承受极限载荷至少3秒钟而不破坏",
        "authority": "CAAC"
    },

    # ---------------------------
    # 规范性文件层 (第一章重构内容)
    # ---------------------------
    {
        "code": "AC-21-AA-2023-15",
        "title": "复合材料结构符合性方法咨询通告",
        "content": "复合材料结构适航符合性验证方法指南",
        "authority": "CAAC"
    },
    {
        "code": "AP-21-AA-2021-06",
        "title": "复合材料结构审查程序",
        "content": "复合材料结构适航审查管理程序",
        "authority": "CAAC"
    },

    # ---------------------------
    # 复合材料核心规范 (第一章重构内容)
    # ---------------------------
    {
        "code": "AC-20-107B",
        "title": "AC20-107B",
        "content": "FAA复合材料飞机结构符合性方法指南",
        "authority": "FAA"
    }
]

# ----------------------------
# Concepts - 第一章使用重构后的概念定义
# ----------------------------
CONCEPTS = [
    # 第一章重构内容 - 总结构
    {"name": "适航法规体系", "level": "结构", "description": "民用航空器适航管理的法规层级体系"},
    {"name": "复合材料结构适航规范", "level": "结构", "description": "复合材料结构特有的适航规范要求"},

    # 第一章重构内容 - 法规层级结构
    {"name": "法律层", "level": "法规层级", "description": "适航管理的最高法律依据"},
    {"name": "行政法规层", "level": "法规层级", "description": "国务院制定的适航管理行政法规"},
    {"name": "规章层", "level": "法规层级", "description": "民航局制定的适航规章（CCAR系列）"},
    {"name": "规范性文件层", "level": "法规层级", "description": "咨询通告（AC）、管理程序（AP）等指导文件"},

    # 原有概念保持不变（第2-9章使用）
    {"name": "积木式验证", "level": "方法", "description": "从试样到全尺寸试验的渐进验证方法"},
    {"name": "B基准值", "level": "统计", "description": "具有95%置信度和90%存活率的结构材料性能值"},
    {"name": "工艺鉴定", "level": "制造", "description": "证明制造工艺能够持续生产符合设计要求产品"},
    {"name": "损伤容限", "level": "设计", "description": "结构在存在损伤时仍能保持其剩余强度和刚度的能力"},
    {"name": "持续适航", "level": "运维", "description": "在飞机整个寿命周期内保持适航标准"},

    # 安全工程相关概念
    {"name": "安全性分析", "level": "安全工程",
     "description": "通过系统化识别危害、评估风险并提出安全需求/措施，形成可审查的安全证据链"},
    {"name": "危害分析", "level": "安全工程", "description": "识别危险源/危害及其触发条件、后果与控制要点"},
    {"name": "风险评估", "level": "安全工程", "description": "对危害的严重性与发生概率等进行评估并确定风险等级"},
    {"name": "安全需求", "level": "安全工程", "description": "由风险评估导出的安全约束/功能/性能要求"},
    {"name": "缓解措施", "level": "安全工程", "description": "用于降低风险的设计/工艺/程序/运维控制措施"},
    {"name": "安全证据", "level": "安全工程", "description": "支持安全结论的证据集合（试验、分析、检查、审查记录等）"},

    # 验证与确认相关概念
    {"name": "地面试验", "level": "验证",
     "description": "在地面环境下开展的验证/确认活动（静力、疲劳、系统联调、功能、环境等）"},
    {"name": "试验计划", "level": "验证", "description": "定义试验目标、覆盖条款/需求、方法、资源、判据与数据管理"},
    {"name": "试验规程", "level": "验证", "description": "可执行的试验步骤、配置基线、仪器设置、数据采集与安全注意事项"},
    {"name": "试验报告", "level": "验证", "description": "试验实施与结果的正式记录，用于审查与证据归档"},

    # 合规相关概念
    {"name": "符合性说明", "level": "合规", "description": "面向条款/要求的符合性陈述及其依据（通常引用矩阵与证据包）"},
    {"name": "认证依据", "level": "合规",
     "description": "适用的法规/条款/咨询通告等构成的符合性基础（certification basis）"},
    {"name": "符合性矩阵", "level": "合规", "description": "条款→要求→方法→证据的结构化映射（便于审查与追溯）"},
    {"name": "符合性证据", "level": "合规", "description": "用于支持符合性结论的证据集合（试验、分析、检验、评审记录等）"},

    # 设备合格性相关概念
    {"name": "设备合格性", "level": "合格性",
     "description": "证明设备/系统满足规定功能与环境适用性等要求（qualification/approval）"},
    {"name": "合格性计划", "level": "合格性", "description": "规定设备合格性范围、方法、判据、样机/批次与数据要求"},
    {"name": "合格性方法", "level": "合格性", "description": "设备合格性采用的方式（试验/分析/检查/相似性论证等）"},
    {"name": "合格性报告", "level": "合格性", "description": "设备合格性活动的结果汇总与结论记录"},
    {"name": "生产验收放行", "level": "合格性", "description": "制造/装配后的验收与放行记录，使产品进入运行/交付阶段"},

    # 管理保障相关概念
    {"name": "保证论证", "level": "管理保障",
     "description": "将证据组织成可审查的论证结构（例如 safety/assurance case）"},
    {"name": "构型与变更管理", "level": "管理保障",
     "description": "对基线、构型、变更影响进行控制并触发必要的再验证/再分析"},
    {"name": "质量管理", "level": "管理保障", "description": "通过过程控制、审核与独立性要求确保数据与活动可信"},
    {"name": "可追溯性", "level": "管理保障", "description": "需求/条款→设计→实现→验证→证据的双向追溯能力"},
]

COMPLIANCE_METHODS = [
    {"code": "MC1", "name": "符合性说明", "description": "通过说明满足条款要求"},
    {"code": "MC2", "name": "计算分析", "description": "通过工程计算证明符合性"},
    {"code": "MC3", "name": "安全性分析", "description": "通过安全性评估证明符合性"},
    {"code": "MC4", "name": "试验室试验", "description": "通过试验证明符合性"},
    {"code": "MC5", "name": "地面试验", "description": "通过地面试验证明符合性"},
    {"code": "MC9", "name": "设备合格性", "description": "通过设备合格性证明符合性"},
]

BUILDING_BLOCKS = [
    {"level": 1, "name": "试样级", "description": "材料基本性能测试"},
    {"level": 2, "name": "元件级", "description": "简单结构件验证"},
    {"level": 3, "name": "细节件级", "description": "典型细节特征验证"},
    {"level": 4, "name": "组合件级", "description": "子结构验证"},
    {"level": 5, "name": "部件级", "description": "全尺寸部件验证"},
]


class AviationKnowledgeGraph:
    def __init__(self) -> None:
        self.conn = Neo4jConnection()

    def close(self) -> None:
        self.conn.close()

    def clear_database(self) -> None:
        self.conn.execute_query("MATCH (n) DETACH DELETE n")
        logger.warning("数据库已清空")

    def create_schema(self) -> None:
        """
        注意：Concept.name UNIQUE 可能与旧的 (:Concept {name}) 普通索引冲突
        - 如果你希望脚本自动修复：设置环境变量 KG_SCHEMA_FIX=true
        """
        base = [
            "CREATE CONSTRAINT chapter_unique IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT article_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.code IS UNIQUE",
            "CREATE CONSTRAINT method_unique IF NOT EXISTS FOR (m:ComplianceMethod) REQUIRE m.code IS UNIQUE",
            "CREATE CONSTRAINT bb_unique IF NOT EXISTS FOR (b:BuildingBlock) REQUIRE b.level IS UNIQUE",
        ]
        for q in base:
            self.conn.execute_query(q)

        try:
            self.conn.execute_query(
                "CREATE CONSTRAINT concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE"
            )
        except Exception as e:
            msg = str(e)
            if ("IndexAlreadyExists" in msg or "constraint conflicts with existing index" in msg):
                if os.getenv("KG_SCHEMA_FIX", "false").lower() in {"1", "true", "yes"}:
                    logger.warning("Concept.name 约束与既有索引冲突，KG_SCHEMA_FIX=true，开始自动修复…")
                    indexes = self.conn.execute_query(
                        """
                        SHOW INDEXES YIELD name, labelsOrTypes, properties
                        WHERE labelsOrTypes = ['Concept'] AND properties = ['name']
                        RETURN name
                        """
                    )
                    for row in indexes:
                        idx_name = row["name"]
                        logger.warning("Dropping conflicting index: %s", idx_name)
                        self.conn.execute_query(f"DROP INDEX {idx_name}")
                    self.conn.execute_query(
                        "CREATE CONSTRAINT concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE"
                    )
                else:
                    raise RuntimeError(
                        "检测到 (:Concept {name}) 索引与 Concept.name UNIQUE 冲突。"
                        "如需自动修复请设置 KG_SCHEMA_FIX=true，或手动 DROP 冲突索引。"
                    ) from e
            else:
                raise

        logger.info("Schema created/verified.")

    def create_aviation_structure(self) -> None:
        self.create_schema()
        self._upsert_nodes()
        self._upsert_relationships()
        logger.info("适航复合材料结构知识图谱（1-9章）创建完成，第一章使用重构后的层级化结构。")

    def _upsert_nodes(self) -> None:
        self.conn.execute_query(
            """
            UNWIND $rows AS row
            MERGE (c:Chapter {id: row.id})
            SET c.title = row.title,
                c.description = row.description
            """,
            {"rows": CHAPTERS},
        )
        self.conn.execute_query(
            """
            UNWIND $rows AS row
            MERGE (a:Article {code: row.code})
            SET a.title = row.title,
                a.content = row.content,
                a.authority = row.authority
            """,
            {"rows": ARTICLES},
        )
        self.conn.execute_query(
            """
            UNWIND $rows AS row
            MERGE (c:Concept {name: row.name})
            SET c.level = row.level,
                c.description = row.description
            """,
            {"rows": CONCEPTS},
        )
        self.conn.execute_query(
            """
            UNWIND $rows AS row
            MERGE (m:ComplianceMethod {code: row.code})
            SET m.name = row.name,
                m.description = row.description
            """,
            {"rows": COMPLIANCE_METHODS},
        )
        self.conn.execute_query(
            """
            UNWIND $rows AS row
            MERGE (b:BuildingBlock {level: row.level})
            SET b.name = row.name,
                b.description = row.description
            """,
            {"rows": BUILDING_BLOCKS},
        )

    def _upsert_relationships(self) -> None:
        # =====================================================
        # 第一章使用重构后的层级化关系
        # =====================================================

        # 第一章包含两个结构块
        self.conn.execute_query("""
        MATCH (c:Chapter {id:1})
        MATCH (s:Concept {name:'适航法规体系'})
        MATCH (m:Concept {name:'复合材料结构适航规范'})
        MERGE (c)-[:INCLUDES]->(s)
        MERGE (c)-[:INCLUDES]->(m)
        """)

        # 法规层级结构
        self.conn.execute_query("""
        MATCH (s:Concept {name:'适航法规体系'})
        MATCH (l:Concept {name:'法律层'})
        MATCH (a:Concept {name:'行政法规层'})
        MATCH (r:Concept {name:'规章层'})
        MATCH (f:Concept {name:'规范性文件层'})
        MERGE (s)-[:HAS_LEVEL]->(l)
        MERGE (s)-[:HAS_LEVEL]->(a)
        MERGE (s)-[:HAS_LEVEL]->(r)
        MERGE (s)-[:HAS_LEVEL]->(f)
        """)

        # 各层包含法规
        self.conn.execute_query("""
        MATCH (l:Concept {name:'法律层'})
        MATCH (law:Article {code:'AVIATION_LAW'})
        MERGE (l)-[:INCLUDES]->(law)
        """)

        self.conn.execute_query("""
        MATCH (a:Concept {name:'行政法规层'})
        MATCH (reg:Article {code:'AIRWORTHINESS_REGULATION'})
        MERGE (a)-[:INCLUDES]->(reg)
        """)

        self.conn.execute_query("""
        MATCH (r:Concept {name:'规章层'})
        MATCH (c21:Article {code:'CCAR-21'})
        MATCH (c25:Article {code:'CCAR-25-R4'})
        MERGE (r)-[:INCLUDES]->(c21)
        MERGE (r)-[:INCLUDES]->(c25)
        """)

        self.conn.execute_query("""
        MATCH (f:Concept {name:'规范性文件层'})
        MATCH (ac:Article {code:'AC-21-AA-2023-15'})
        MATCH (ap:Article {code:'AP-21-AA-2021-06'})
        MERGE (f)-[:INCLUDES]->(ac)
        MERGE (f)-[:INCLUDES]->(ap)
        """)

        # CCAR-25 条款隶属关系
        self.conn.execute_query("""
        MATCH (c25:Article {code:'CCAR-25-R4'})
        MATCH (a301:Article {code:'CCAR-25.301'})
        MATCH (a305:Article {code:'CCAR-25.305'})
        MERGE (c25)-[:CONTAINS]->(a301)
        MERGE (c25)-[:CONTAINS]->(a305)
        """)

        # 复合材料结构适航规范结构
        self.conn.execute_query("""
        MATCH (m:Concept {name:'复合材料结构适航规范'})
        MATCH (c25:Article {code:'CCAR-25-R4'})
        MATCH (ac107:Article {code:'AC-20-107B'})
        MERGE (m)-[:BASED_ON]->(c25)
        MERGE (m)-[:GUIDED_BY]->(ac107)
        """)

        # =====================================================
        # 第2-9章使用原有关系结构
        # =====================================================

        # NEXT_CHAPTER (第2-9章)
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Chapter {id: p.from}), (c2:Chapter {id: p.to})
            MERGE (c1)-[:NEXT_CHAPTER]->(c2)
            """,
            {"pairs": [{"from": i, "to": i + 1} for i in range(1, 9)]},
        )

        # 第2-9章的REFERENCES关系
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c:Chapter {id: p.chapter}), (a:Article {code: p.article})
            MERGE (c)-[:REFERENCES]->(a)
            """,
            {"pairs": [
                # 第2章关联
                {"chapter": 2, "article": "CCAR-21"},
                {"chapter": 2, "article": "CCAR-25-R4"},
                {"chapter": 2, "article": "AC-20-107B"},
                # 第3章关联
                {"chapter": 3, "article": "CCAR-25.301"},
                {"chapter": 3, "article": "CCAR-25.305"},
                # 其他章节关联...
            ]},
        )

        # 第2-9章的INCLUDES关系
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c:Chapter {id: p.chapter}), (con:Concept {name: p.concept})
            MERGE (c)-[:INCLUDES]->(con)
            """,
            {"pairs": [
                # 第2章概念
                {"chapter": 2, "concept": "符合性说明"},
                {"chapter": 2, "concept": "安全性分析"},
                {"chapter": 2, "concept": "地面试验"},
                {"chapter": 2, "concept": "设备合格性"},
                # 第3章概念
                {"chapter": 3, "concept": "B基准值"},
                # 第4章概念
                {"chapter": 4, "concept": "工艺鉴定"},
                # 第7章概念
                {"chapter": 7, "concept": "积木式验证"},
                # 第8章概念
                {"chapter": 8, "concept": "损伤容限"},
                {"chapter": 8, "concept": "持续适航"},
                # 其他章节概念...
            ]},
        )

        # BuildingBlock NEXT_LEVEL (第7章使用)
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (b1:BuildingBlock {level: p.from}), (b2:BuildingBlock {level: p.to})
            MERGE (b1)-[:NEXT_LEVEL]->(b2)
            """,
            {"pairs": [{"from": i, "to": i + 1} for i in range(1, 5)]},
        )

        # Chapter USES_METHOD (第7章使用)
        self.conn.execute_query(
            """
            MATCH (c:Chapter {id: 7}), (b:BuildingBlock {level: 1})
            MERGE (c)-[:USES_METHOD]->(b)
            """
        )

        # CAN_COMPLY_WITH
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (a:Article {code: p.article}), (m:ComplianceMethod {code: p.method})
            MERGE (a)-[:CAN_COMPLY_WITH]->(m)
            """,
            {"pairs": [
                {"article": "CCAR-25.301", "method": "MC2"},
                {"article": "CCAR-25.301", "method": "MC4"},
                {"article": "CCAR-25.305", "method": "MC4"},
            ]},
        )


if __name__ == "__main__":
    kg = AviationKnowledgeGraph()
    try:
        # 如需清空重建：先执行 kg.clear_database()
        kg.create_aviation_structure()
    finally:
        kg.close()