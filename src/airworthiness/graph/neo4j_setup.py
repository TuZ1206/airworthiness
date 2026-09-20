# neo4j_setup.py (web-compatible refined version)
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
# Data (Ch1–Ch9)
# ----------------------------
CHAPTERS = [
    {"id": 1, "title": "适航法规体系与复合材料结构概论",
     "description": "民用航空器适航法规体系框架与复合材料结构适航规范要求"},
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

ARTICLES = [
    # 适航法规体系 - 法律层
    {"code": "AVIATION_LAW", "title": "《中华人民共和国民用航空法》",
     "content": "民用航空器适航管理的最高法律依据", "authority": "全国人大常委会"},

    # 适航法规体系 - 行政法规层
    {"code": "AVIATION_REGULATION", "title": "《民用航空器适航管理条例》",
     "content": "国务院制定的民用航空器适航管理行政法规", "authority": "国务院"},

    # 适航法规体系 - 规章层（CCAR）
    {"code": "CCAR-21", "title": "民用航空产品和零部件合格审定规定",
     "content": "民用航空产品合格审定的基本规章", "authority": "CAAC"},
    {"code": "CCAR-25-R4", "title": "运输类飞机适航标准",
     "content": "运输类飞机结构强度和环境适应性要求", "authority": "CAAC"},
    {"code": "CCAR-23", "title": "正常类飞机适航标准",
     "content": "正常类飞机结构强度和环境适应性要求", "authority": "CAAC"},

    # 适航法规体系 - 规范性文件层
    {"code": "AC-21-AA-2023-15", "title": "复合材料结构适航符合性方法",
     "content": "复合材料结构符合性验证方法指南", "authority": "CAAC"},
    {"code": "AP-21-AA-2021-06", "title": "复合材料结构审查程序",
     "content": "复合材料结构适航审查管理程序", "authority": "CAAC"},

    # 复合材料结构适航规范
    {"code": "AC-20-107B", "title": "复合材料飞机结构",
     "content": "FAA关于复合材料结构适航符合性方法指南", "authority": "FAA"},
    {"code": "CCAR-25.301", "title": "载荷条件",
     "content": "结构必须能够承受限制载荷而无有害永久变形", "authority": "CAAC"},
    {"code": "CCAR-25.305", "title": "强度和变形",
     "content": "结构必须能够承受极限载荷至少3秒钟而不破坏", "authority": "CAAC"},
]

# ----------------------------
# Concepts (基础概念 + 细化后的保证/合规链路概念)
# - 为避免误分：所有新增节点均以 :Concept 承载，level 仅作“类别标注”，不强行本体化
# ----------------------------
CONCEPTS = [
    # 原有
    {"name": "积木式验证", "level": "方法", "description": "从试样到全尺寸试验的渐进验证方法"},
    {"name": "B基准值", "level": "统计", "description": "具有95%置信度和90%存活率的结构材料性能值"},
    {"name": "工艺鉴定", "level": "制造", "description": "证明制造工艺能够持续生产符合设计要求产品"},
    {"name": "损伤容限", "level": "设计", "description": "结构在存在损伤时仍能保持其剩余强度和刚度的能力"},
    {"name": "持续适航", "level": "运维", "description": "在飞机整个寿命周期内保持适航标准"},

    # 新增：安全工程（Safety Engineering）
    {"name": "安全性分析", "level": "安全工程", "description": "通过系统化识别危害、评估风险并提出安全需求/措施，形成可审查的安全证据链"},
    {"name": "危害分析", "level": "安全工程", "description": "识别危险源/危害及其触发条件、后果与控制要点"},
    {"name": "风险评估", "level": "安全工程", "description": "对危害的严重性与发生概率等进行评估并确定风险等级"},
    {"name": "安全需求", "level": "安全工程", "description": "由风险评估导出的安全约束/功能/性能要求"},
    {"name": "缓解措施", "level": "安全工程", "description": "用于降低风险的设计/工艺/程序/运维控制措施"},
    {"name": "安全证据", "level": "安全工程", "description": "支持安全结论的证据集合（试验、分析、检查、审查记录等）"},

    # 新增：验证与确认（V&V）中的地面验证
    {"name": "地面试验", "level": "验证", "description": "在地面环境下开展的验证/确认活动（静力、疲劳、系统联调、功能、环境等）"},
    {"name": "试验计划", "level": "验证", "description": "定义试验目标、覆盖条款/需求、方法、资源、判据与数据管理"},
    {"name": "试验规程", "level": "验证", "description": "可执行的试验步骤、配置基线、仪器设置、数据采集与安全注意事项"},
    {"name": "试验报告", "level": "验证", "description": "试验实施与结果的正式记录，用于审查与证据归档"},

    # 新增：合规/符合性（Compliance）
    {"name": "符合性说明", "level": "合规", "description": "面向条款/要求的符合性陈述及其依据（通常引用矩阵与证据包）"},
    {"name": "认证依据", "level": "合规", "description": "适用的法规/条款/咨询通告等构成的符合性基础（certification basis）"},
    {"name": "符合性矩阵", "level": "合规", "description": "条款→要求→方法→证据的结构化映射（便于审查与追溯）"},
    {"name": "符合性证据", "level": "合规", "description": "用于支持符合性结论的证据集合（试验、分析、检验、评审记录等）"},

    # 新增：设备合格性（Qualification）
    {"name": "设备合格性", "level": "合格性", "description": "证明设备/系统满足规定功能与环境适用性等要求（qualification/approval）"},
    {"name": "合格性计划", "level": "合格性", "description": "规定设备合格性范围、方法、判据、样机/批次与数据要求"},
    {"name": "合格性方法", "level": "合格性", "description": "设备合格性采用的方式（试验/分析/检查/相似性论证等）"},
    {"name": "合格性报告", "level": "合格性", "description": "设备合格性活动的结果汇总与结论记录"},
    {"name": "生产验收放行", "level": "合格性", "description": "制造/装配后的验收与放行记录，使产品进入运行/交付阶段"},

    # 新增：管理保障（Management & Assurance）
    {"name": "保证论证", "level": "管理保障", "description": "将证据组织成可审查的论证结构（例如 safety/assurance case）"},
    {"name": "构型与变更管理", "level": "管理保障", "description": "对基线、构型、变更影响进行控制并触发必要的再验证/再分析"},
    {"name": "质量管理", "level": "管理保障", "description": "通过过程控制、审核与独立性要求确保数据与活动可信"},
    {"name": "可追溯性", "level": "管理保障", "description": "需求/条款→设计→实现→验证→证据的双向追溯能力"},
]

CONCEPTS.extend([
    # =========================
    # 第一章：法规体系（顶层 -> 分层）
    # =========================
    {"name": "适航法规体系", "level": "法规体系", "description": "民用航空器适航管理的法规文件层级框架（法律、行政法规、规章、规范性文件）"},

    {"name": "法律层", "level": "法规体系", "description": "适航管理的最高法律依据，如《中华人民共和国民用航空法》"},
    {"name": "行政法规层", "level": "法规体系", "description": "国务院制定的民用航空器适航管理行政法规，如《民用航空器适航管理条例》"},
    {"name": "规章层", "level": "法规体系", "description": "民航局制定的部门规章（CCAR 系列），用于实施适航管理与标准要求"},
    {"name": "规范性文件层", "level": "法规体系", "description": "咨询通告（AC）、管理程序（AP）等规范性文件，提供实施路径与指导"},

    # =========================
    # 第一章：复合材料结构适航规范（顶层 -> 两大来源）
    # =========================
    {"name": "复合材料结构适航规范", "level": "适航要求", "description": "针对复合材料结构设计、制造、验证与持续适航的适航符合性规范体系"},
    {"name": "复合材料结构适航规范（AC-20-107B）", "level": "符合性指南", "description": "以 FAA AC-20-107B 为核心的复合材料结构符合性方法与考虑要点"},
    {"name": "复合材料结构适航规范（CCAR-25-R4）", "level": "适航标准", "description": "以 CCAR-25-R4 为核心的运输类飞机结构适航标准与条款要求"},
])

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
        logger.info("适航复合材料结构知识图谱（1-9章）创建完成。")

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
        # NEXT_CHAPTER
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Chapter {id: p.from}), (c2:Chapter {id: p.to})
            MERGE (c1)-[:NEXT_CHAPTER]->(c2)
            """,
            {"pairs": [{"from": i, "to": i + 1} for i in range(1, 9)]},
        )

        # REFERENCES
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c:Chapter {id: p.chapter}), (a:Article {code: p.article})
            MERGE (c)-[:REFERENCES]->(a)
            """,
            {"pairs": [
            ]},
        )

        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c:Chapter {id: p.chapter}), (con:Concept {name: p.concept})
            MERGE (c)-[:INCLUDES]->(con)
            """,
            {"pairs": [
                {"chapter": 1, "concept": "适航法规体系"},
                {"chapter": 1, "concept": "复合材料结构适航规范"},
            ]},
        )

        # ============================================================
        # 第一章：结构层级（HAS_LEVEL）
        #   适航法规体系 -> 法律层/行政法规层/规章层/规范性文件层
        #   复合材料结构适航规范 -> (AC-20-107B)/(CCAR-25-R4)
        # ============================================================
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Concept {name: p.from}), (c2:Concept {name: p.to})
            MERGE (c1)-[:HAS_LEVEL]->(c2)
            """,
            {"pairs": [
                # 法规体系四层
                {"from": "适航法规体系", "to": "法律层"},
                {"from": "适航法规体系", "to": "行政法规层"},
                {"from": "适航法规体系", "to": "规章层"},
                {"from": "适航法规体系", "to": "规范性文件层"},

                # 复合材料结构适航规范两大来源
                {"from": "复合材料结构适航规范", "to": "复合材料结构适航规范（AC-20-107B）"},
                {"from": "复合材料结构适航规范", "to": "复合材料结构适航规范（CCAR-25-R4）"},
            ]},
        )

        # ============================================================
        # 第一章：分层概念 -> INCLUDES -> Article（把文件挂在对应层级上）
        #   注意：这里严格按你给的分类，不做不确定扩展
        # ============================================================
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (con:Concept {name: p.concept}), (a:Article {code: p.article})
            MERGE (con)-[:INCLUDES]->(a)
            """,
            {"pairs": [
                # 法律层
                {"concept": "法律层", "article": "AVIATION_LAW"},

                # 行政法规层
                {"concept": "行政法规层", "article": "AVIATION_REGULATION"},

                # 规章层（CCAR）
                {"concept": "规章层", "article": "CCAR-21"},
                {"concept": "规章层", "article": "CCAR-25-R4"},
                {"concept": "规章层", "article": "CCAR-23"},

                # 规范性文件层（AC/AP等）
                {"concept": "规范性文件层", "article": "AC-21-AA-2023-15"},
                {"concept": "规范性文件层", "article": "AP-21-AA-2021-06"},

                # 复合材料结构适航规范：AC20-107B
                {"concept": "复合材料结构适航规范（AC-20-107B）", "article": "AC-20-107B"},

                # 复合材料结构适航规范：CCAR-25-R4（以及你当前列出的具体条款）
                {"concept": "复合材料结构适航规范（CCAR-25-R4）", "article": "CCAR-25-R4"},
                {"concept": "复合材料结构适航规范（CCAR-25-R4）", "article": "CCAR-25.301"},
                {"concept": "复合材料结构适航规范（CCAR-25-R4）", "article": "CCAR-25.305"},
            ]},
        )

        # INCLUDES（原有 + 把关键“孤立项”挂回章节语境）
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c:Chapter {id: p.chapter}), (con:Concept {name: p.concept})
            MERGE (c)-[:INCLUDES]->(con)
            """,
            {"pairs": [
                {"chapter": 3, "concept": "B基准值"},
                {"chapter": 4, "concept": "工艺鉴定"},
                {"chapter": 7, "concept": "积木式验证"},
                {"chapter": 8, "concept": "损伤容限"},
                {"chapter": 8, "concept": "持续适航"},

                # 新增：把“安全性分析/地面/符合性说明/设备合格性”与框架章节关联
                {"chapter": 2, "concept": "符合性说明"},
                {"chapter": 2, "concept": "安全性分析"},
                {"chapter": 2, "concept": "地面试验"},
                {"chapter": 2, "concept": "设备合格性"},
                {"chapter": 2, "concept": "符合性矩阵"},
                {"chapter": 2, "concept": "符合性证据"},
                {"chapter": 2, "concept": "保证论证"},
                {"chapter": 5, "concept": "构型与变更管理"},
                {"chapter": 6, "concept": "质量管理"},
                {"chapter": 6, "concept": "可追溯性"},
                {"chapter": 9, "concept": "符合性说明"},
            ]},
        )

        # BuildingBlock NEXT_LEVEL
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (b1:BuildingBlock {level: p.from}), (b2:BuildingBlock {level: p.to})
            MERGE (b1)-[:NEXT_LEVEL]->(b2)
            """,
            {"pairs": [{"from": i, "to": i + 1} for i in range(1, 5)]},
        )

        # Chapter USES_METHOD
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

        # ============================================================
        # 新增：把 ComplianceMethod 与细化概念对齐（解决“孤立节点”）
        # ============================================================
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (m:ComplianceMethod {code: p.method}), (c:Concept {name: p.concept})
            MERGE (m)-[:ALIGNS_WITH]->(c)
            """,
            {"pairs": [
                {"method": "MC1", "concept": "符合性说明"},
                {"method": "MC3", "concept": "安全性分析"},
                {"method": "MC5", "concept": "地面试验"},
                {"method": "MC9", "concept": "设备合格性"},
            ]},
        )

        # ============================================================
        # 新增：学术共识下的“证据链”初步细化（只做稳妥不误分的关系）
        # ============================================================

        # 安全工程链：安全性分析 -> 危害分析 -> 风险评估 -> 安全需求 -> 缓解措施
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Concept {name: p.from}), (c2:Concept {name: p.to})
            MERGE (c1)-[:DECOMPOSES_TO]->(c2)
            """,
            {"pairs": [
                {"from": "安全性分析", "to": "危害分析"},
                {"from": "危害分析", "to": "风险评估"},
                {"from": "风险评估", "to": "安全需求"},
                {"from": "安全需求", "to": "缓解措施"},
            ]},
        )

        # 地面试验活动链：地面试验 -> 试验计划 -> 试验规程 -> 试验报告
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Concept {name: p.from}), (c2:Concept {name: p.to})
            MERGE (c1)-[:HAS_ARTIFACT]->(c2)
            """,
            {"pairs": [
                {"from": "地面试验", "to": "试验计划"},
                {"from": "试验计划", "to": "试验规程"},
                {"from": "试验规程", "to": "试验报告"},
            ]},
        )

        # 合规链：认证依据 -> 符合性矩阵 -> 符合性说明；符合性证据支撑符合性说明
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Concept {name: p.from}), (c2:Concept {name: p.to})
            MERGE (c1)-[:STRUCTURES]->(c2)
            """,
            {"pairs": [
                {"from": "认证依据", "to": "符合性矩阵"},
                {"from": "符合性矩阵", "to": "符合性说明"},
            ]},
        )
        self.conn.execute_query(
            """
            MATCH (e:Concept {name:'符合性证据'}), (s:Concept {name:'符合性说明'})
            MERGE (e)-[:SUPPORTS]->(s)
            """
        )

        # 试验报告/安全分析/设备合格性均可贡献证据（稳妥建模：贡献到“符合性证据/安全证据”集合）
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (src:Concept {name: p.src}), (dst:Concept {name: p.dst})
            MERGE (src)-[:CONTRIBUTES_TO_EVIDENCE]->(dst)
            """,
            {"pairs": [
                {"src": "试验报告", "dst": "符合性证据"},
                {"src": "安全性分析", "dst": "安全证据"},
                {"src": "地面试验", "dst": "安全证据"},
                {"src": "设备合格性", "dst": "符合性证据"},
            ]},
        )

        # 设备合格性链：设备合格性 -> 合格性计划 -> 合格性方法 -> 合格性报告 -> 生产验收放行
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (c1:Concept {name: p.from}), (c2:Concept {name: p.to})
            MERGE (c1)-[:HAS_QUALIFICATION_FLOW]->(c2)
            """,
            {"pairs": [
                {"from": "设备合格性", "to": "合格性计划"},
                {"from": "合格性计划", "to": "合格性方法"},
                {"from": "合格性方法", "to": "合格性报告"},
                {"from": "合格性报告", "to": "生产验收放行"},
            ]},
        )

        # 管理保障：构型与变更管理 触发安全性分析/地面试验/设备合格性的再执行；质量管理审核关键产物；保证论证索引证据
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (m:Concept {name:'构型与变更管理'}), (t:Concept {name: p.target})
            MERGE (m)-[:TRIGGERS_REASSESSMENT_OF]->(t)
            """,
            {"pairs": [
                {"target": "安全性分析"},
                {"target": "地面试验"},
                {"target": "设备合格性"},
                {"target": "符合性说明"},
            ]},
        )
        self.conn.execute_query(
            """
            UNWIND $pairs AS p
            MATCH (q:Concept {name:'质量管理'}), (t:Concept {name: p.target})
            MERGE (q)-[:REVIEWS]->(t)
            """,
            {"pairs": [
                {"target": "试验计划"},
                {"target": "试验规程"},
                {"target": "试验报告"},
                {"target": "符合性说明"},
                {"target": "合格性报告"},
            ]},
        )
        self.conn.execute_query(
            """
            MATCH (ac:Concept {name:'保证论证'}), (ce:Concept {name:'符合性证据'}), (se:Concept {name:'安全证据'})
            MERGE (ac)-[:INDEXES_EVIDENCE]->(ce)
            MERGE (ac)-[:INDEXES_EVIDENCE]->(se)
            """
        )


if __name__ == "__main__":
    kg = AviationKnowledgeGraph()
    try:
        # 如需清空重建：先执行 kg.clear_database()
        kg.create_aviation_structure()
    finally:
        kg.close()
