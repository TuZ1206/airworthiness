from flask import Flask, render_template, request, jsonify, send_file
from neo4j_setup import AviationKnowledgeGraph
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

load_dotenv()

app = Flask(__name__)
kg = AviationKnowledgeGraph()
fixed_chapter_data = {
    1: {  # 第1章：复合材料适航法规体系概论
        "id": 1,
        "title": "复合材料适航法规体系概论",
        "description": "本章系统阐述了航空器与适航的基本定义、民用航空器完整的适航审定与管理流程（涵盖型号合格、生产许可、持续适航），并概述了复合材料结构在适航符合性验证中的核心特性、验证方法与特殊考量。",
        "prev_chapter": None,
        "next_chapter": {"id": 2, "title": "第二章"},
        # 依据“下一章”按钮链接 (`href="/chapter/2/detail"`) 确定。其标题暂定为通用格式，若已知具体标题可更新。
        "articles": [  # 相关法规 (共7项)
            {"code": "芝加哥公约附件7 & 8", "title": "航空器国籍及登记标记；航空器适航性（国际定义基础）。",
             "content": "..."},
            {"code": "CCAR-45-R1 / 14 CFR §1.1", "title": "中/美对航空器、民用航空器、公共航空器的法定定义。",
             "content": "..."},
            {"code": "CCAR-21 / 14 CFR Part 21", "title": "产品与零部件合格审定的核心管理规章。", "content": "..."},
            {"code": "AP-21-AA-2023-11R1", "title": "型号合格审定程序（CAAC）。", "content": "..."},
            {"code": "AP-21-AA-2023-16", "title": "生产批准和监督程序（CAAC）。", "content": "..."},
            {"code": "AC 20-107B", "title": "复合材料飞机结构（FAA，复合材料验证核心指南）。", "content": "..."},
            {"code": "无人驾驶航空器飞行管理暂行条例", "title": "国务院、中央军委令第761号，中国无人机管理核心法规。",
             "content": "..."}
        ],
        "concepts": [  # 核心概念 (共14项)
            {"name": "航空器 / 飞机", "description": "基于空气动力获得支撑的飞行装置；特指固定翼航空器。", "level": None},
            {"name": "民用航空器 / 公共航空器", "description": "通过排除法界定；在美国指用于非商业政府职能的航空器。",
             "level": None},
            {"name": "适航 (Airworthiness)", "description": "符合经批准的设计并处于安全运行状态。", "level": None},
            {"name": "预期运行条件", "description": "在航空器使用寿命期间可合理想象会发生的条件，用于评估安全运行状态。",
             "level": None},
            {"name": "型号合格审定 (TC)", "description": "对产品设计的批准过程，颁发型号合格证。", "level": None},
            {"name": "生产许可审定 (PC)", "description": "对制造商批量生产符合批准设计产品能力的批准。", "level": None},
            {"name": "审定基础",
             "description": "型号合格证颁发前必须表明符合性的具体规章及其版次，包括专用条件、等效安全结论等。",
             "level": None},
            {"name": "符合性验证方法 (MC0-MC9)", "description": "十种表明符合适航条款的方法，如设计评审、分析、试验等。",
             "level": None},
            {"name": "型号检查核准书 (TIA)", "description": "进行正式审定飞行试验前必须取得的批准文件。", "level": None},
            {"name": "持续适航文件", "description": "支持航空器在全寿命期内安全运行和维修的所有技术文件总和。",
             "level": None},
            {"name": "MSG-3逻辑分析", "description": "确定计划维修任务和间隔的标准分析方法。", "level": None},
            {"name": "结构修理手册 (SRM)", "description": "描述航空器在服役中预期的结构修理种类和准则的批准文件。",
             "level": None},
            {"name": "积木式验证方法", "description": "从简单试样到全尺寸部件的渐进式试验与分析相结合的验证策略。",
             "level": None},
            {"name": "损伤分类 (如BVID)", "description": "根据损伤可检性和威胁，将损伤分为1-5类，并规定不同的验证要求。",
             "level": None}
        ],
        "methods": [  # 合规方法 (共6项)
            {"name": "审定流程执行",
             "description": "严格按照AP-21程序，分阶段（受理、要求确定、计划制定、符合性确认、颁证）完成型号或生产合格审定。",
             "content": "..."},
            {"name": "材料与工艺鉴定",
             "description": "建立并遵守经批准的规范，通过试验鉴定关键工艺，形成包含环境效应的设计数据库。",
             "content": "..."},
            {"name": "积木式验证", "description": "规划和实施从试样到全尺寸部件的分层级试验，结合分析，系统验证结构性能。",
             "content": "..."},
            {"name": "损伤分类与评估",
             "description": "识别所有损伤威胁并进行分类，针对每类损伤执行规定的剩余强度验证和检查要求。",
             "content": "..."},
            {"name": "持续适航文件编制",
             "description": "依据规章编制完整的维修要求、程序和构型控制文件，支持航空器全寿命期安全。", "content": "..."},
            {"name": "单机适航检查",
             "description": "对每架航空器进行文件评审和现场检查，确认其符合经批准的设计并处于安全可用状态。",
             "content": "..."}
        ]
    },
    2: {  # 第2章 (基于detail.html内容)
        "id": 2,
        "title": "复合材料结构适航验证总体框架",
        "description": "本章系统阐述复合材料结构适航验证的核心框架，涵盖符合性方法(MoC)、积木式验证方法、验证证据链构建以及完整的取证与审查流程，为复合材料飞机结构满足适航规章要求提供系统的工程路径。",
        "prev_chapter": {"id": 1, "title": "复合材料适航法规体系概述"},
        "next_chapter": {"id": 3, "title": "复合材料制造与工艺符合性"},
        "articles": [
            {"code": "AP-21-AA-2023-11R1", "title": "型号合格审定程序", "content": "..."},
            {"code": "HB 8605-2021", "title": "飞机复合材料结构适航符合性验证通用要求", "content": "..."},
            {"code": "AC 20-107B", "title": "Composite Aircraft Structure", "content": "..."},
            {"code": "14 CFR Part 25", "title": "运输类飞机适航标准 (示例引用)", "content": "..."}
        ],
        "concepts": [
            {"name": "符合性方法 (MoC)", "description": "表明设计符合适航规章要求的具体工程手段，如MC0-MC9。",
             "level": None},
            {"name": "“积木式”方法",
             "description": "通过从试样到部件的多层级试验与分析，逐步、可靠地确定结构强度的系统方法。", "level": None},
            {"name": "损伤无扩展/缓慢扩展/止裂扩展",
             "description": "复合材料结构损伤容限验证的三种主要设计理念与分析方法。", "level": None},
            {"name": "验证证据链",
             "description": "由试验、分析和检查构成的，用于向审查方证明设计符合性的完整逻辑链条。", "level": None}
        ]
    },
    3: {  # 第3章：复合材料的材料性能及验证
        "id": 3,
        "title": "复合材料的材料性能及验证",
        "description": "本章详细阐述了复合材料在民用飞机适航审定中，关于材料性能表征、统计评估方法、验证标准及材料规范的量化要求与技术指标。",
        "prev_chapter": {"id": 2, "title": "复合材料结构适航验证总体框架"},  # 与第2章关联
        "next_chapter": {"id": 4, "title": "第四章 复合材料的工艺及验证"},  # 与第4章关联
        "articles": [  # 相关法规
            {"code": "CCAR-25-R4 25.303", "title": "材料性能统计评估与设计许用值确定", "content": "..."},
            {"code": "CAAC AC 20-107B", "title": "复合材料飞机结构，包含材料、工艺、验证与审定", "content": "..."},
            {"code": "HB 8605-2021", "title": "民用飞机复合材料结构工艺质量控制", "content": "..."},
            {"code": "SAE AMS 3700", "title": "预浸料材料规范行业标准", "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "材料适航标准", "description": "适用于复合材料性能表征与验证的法规和行业标准", "level": None},
            {"name": "材料性能表征", "description": "通过标准化测试方法量化材料力学性能与环境适应性",
             "level": None},
            {"name": "统计基准值",
             "description": "基于统计分布（如威布尔分布）计算的、具有特定置信水平和存活率的设计许用值（A/B基准值）",
             "level": None},
            {"name": "材料规范", "description": "规定原材料、预浸料、成型材料技术指标、验收标准与管控要求的文件",
             "level": None},
            {"name": "材料资质鉴定 (MQR)", "description": "对复合材料体系从原材料到成型材料进行全性能验证的过程",
             "level": None}
        ]
    },
    4: {  # 第4章：复合材料的工艺及验证
        "id": 4,
        "title": "复合材料的工艺及验证",
        "description": "本章系统阐述了复合材料构件制造工艺的适航标准、关键工艺参数控制、过程质量控制方法、工艺验证要求及相应文件化规范，确保生产过程的稳定性和构件的适航符合性。",
        "prev_chapter": {"id": 3, "title": "第三章 复合材料的材料性能及验证"},  # 与第3章关联
        "next_chapter": {"id": 5, "title": "第五章 等同验证与变更管理"},
        "articles": [  # 相关法规
            {"code": "CCAR-25-R4 25.831", "title": "工艺要求与工艺变更的适航审定要求", "content": "..."},
            {"code": "CAAC AC 20-107B 6", "title": "复合材料的制造与工艺验证要求", "content": "..."},
            {"code": "HB 7736-2004", "title": "飞机复合材料构件制造工艺质量控制要求", "content": "..."},
            {"code": "HB 8605-2021", "title": "民用飞机复合材料结构工艺质量控制（部分条款）", "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "工艺适航标准",
             "description": "确保复合材料制造工艺满足安全性、一致性和可重复性的法规与行业标准。", "level": None},
            {"name": "固化与压实工艺",
             "description": "通过控制温度、压力、真空度等参数，使树脂基体固化并压实增强纤维的关键成型过程。",
             "level": None},
            {"name": "工艺过程控制",
             "description": "对制造过程的关键参数进行实时监控与测量，确保其在规定范围内，以预防缺陷。", "level": None},
            {"name": "工艺验证",
             "description": "通过系统性的试验和评估，证明工艺能够稳定生产出符合设计要求的合格产品。", "level": None},
            {"name": "过程控制文件 (PCD)",
             "description": "用于详细规定和记录生产过程、控制点、偏差处理和质量记录的文件化体系。", "level": None}
        ],
        "methods": [  # 合规方法 (新增字段，与HTML中的“合规方法”板块对应)
            {"name": "工艺验证 (鉴定/稳定性/变更)",
             "description": "通过规定数量的试生产和性能检测，分阶段证明新工艺的可行性、稳定性和变更后的等效性。",
             "content": "..."},
            {"name": "关键参数监控",
             "description": "在固化、铺层等关键工序使用高精度传感器实时监控温度、压力、定位等参数，确保符合工艺规范。",
             "content": "..."},
            {"name": "在线缺陷检测与预警",
             "description": "在铺层和固化过程中应用目视、扫描等手段实时检测缺陷，并设置参数偏差预警阈值，触发额外检查。",
             "content": "..."},
            {"name": "过程控制文件(PCD)管理",
             "description": "编制、维护并定期审核包含流程图、记录表和偏差处理的PCD，确保生产过程全程受控和可追溯。",
             "content": "..."}
        ]
    },
    5: {  # 第5章：等同验证与变更管理
        "id": 5,
        "title": "等同验证与变更管理",
        "description": "本章详细阐述了在航空器设计与制造中，确保材料、工艺、供应商及设计变更符合适航要求的“等同性”验证原则、管理框架与具体实施方法。",
        "prev_chapter": {"id": 4, "title": "第四章 复合材料的工艺及验证"},
        "next_chapter": {"id": 6, "title": "第六章 质量体系与供应链适航监管"},
        "articles": [  # 相关法规
            {"code": "FAR 25.853 / 14 CFR Part 25", "title": "材料可燃性标准，全球等效性基础", "content": "..."},
            {"code": "DOT/FAA/AR-00/47 & 03/19", "title": "聚合物基复合材料材料合格审定与等效性程序",
             "content": "..."},
            {"code": "14 CFR Part 21 / CCAR-21", "title": "产品合格审定与生产批准的核心法规", "content": "..."},
            {"code": "AC 21-43", "title": "FAA生产、供应商控制与变更管理指南", "content": "..."},
            {"code": "NASA-STD-7919.1", "title": "NASA航空器适航、运行、维护与安全综合要求", "content": "..."},
            {"code": "AP-21-AA-2010-04R4", "title": "CAAC生产批准与供应商监督程序", "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "材料等同 (Material Equivalency)",
             "description": "通过标准测试和统计方法，证明新材料或变更后材料在功能和安全上与原批准材料等效。",
             "level": None},
            {"name": "工艺等同 (Process Equivalency)",
             "description": "对制造工艺变更进行评估和验证，确保其产出产品的适航性不受影响。", "level": None},
            {"name": "配置控制 (Configuration Control)",
             "description": "通过文件化和系统化的流程，识别、记录和控制产品（如航空器）的设计状态和变更。",
             "level": None},
            {"name": "生产批准 (Production Approval)",
             "description": "局方对组织按照经批准的设计进行持续、稳定生产的能力的批准，如PC、PMA、POA。", "level": None},
            {"name": "供应商变更管理",
             "description": "对供应链中设计、制造、质量体系的变更进行控制、评估、批准和通知的程序。", "level": None}
        ],
        "methods": [  # 合规方法
            {"name": "变更分类与评估",
             "description": "依据法规（如14 CFR Part 21）对设计、工艺、供应商变更进行“大改/小改”分类，并执行相应的符合性验证和批准流程。",
             "content": "..."},
            {"name": "统计等效性验证",
             "description": "运用统计技术（如依据DOT/FAA/AR文件）对比新老材料数据集，以数值化方式证明性能等同。",
             "content": "..."},
            {"name": "供应商控制程序",
             "description": "建立并执行程序，确保供应商产品符合要求，并包含变更通知、监督和问题报告机制。",
             "content": "..."},
            {"name": "构型管理与记录保存",
             "description": "使用系统（如NAMIS）管理构型基线，确保所有变更、工程文档、符合性记录得到完整记录、批准和可追溯。",
             "content": "..."}
        ]
    },
    6: {
        "id": 6,
        "title": "质量体系与供应链适航监管",
        "description": "本章系统阐述了航空器制造商及其供应商在质量管理体系、生产批准、过程控制、数据追溯等方面的适航监管要求，确保从原材料到最终产品的全供应链符合安全与质量规范。",
        "prev_chapter": {"id": 5, "title": "第五章 等同验证与变更管理"},
        "next_chapter": {"id": 7, "title": "第七章 积木式验证方法"},
        "articles": [  # 相关法规
            {"code": "14 CFR Part 21.137 / AC 21-43", "title": "FAA供应商控制、生产批准与质量管理的核心要求。",
             "content": "..."},
            {"code": "AC 20-154A", "title": "FAA接收检验系统指南。", "content": "..."},
            {"code": "CCAR-21 / AP-21-AA-2010-04R4", "title": "CAAC生产批准、供应商监督与追溯信息报告要求。",
             "content": "..."},
            {"code": "AP-21-31", "title": "CAAC生产许可证(PC)审定程序。", "content": "..."},
            {"code": "NASA-STD-7919.1", "title": "NASA供应商质量管理、质量控制与记录管理的综合要求。",
             "content": "..."},
            {"code": "EASA Part 21 Subpart G", "title": "EASA生产组织批准(POA)要求。", "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "生产批准持有人 (PAH)",
             "description": "持有PC、PMA等生产批准证书，对其产品适航性负最终责任的组织。", "level": None},
            {"name": "生产批准", "description": "局方对组织批量生产符合经批准设计产品的能力的批准，如PC、PMA、POA。",
             "level": None},
            {"name": "供应商控制程序",
             "description": "PAH为确保供应商产品符合要求而建立的管理程序，包括批准、监督和报告机制。", "level": None},
            {"name": "直接发货 (Drop Shipping)",
             "description": "在满足严格条件下，允许供应商直接将货物发往PAH的客户，PAH仍承担适航责任。", "level": None},
            {"name": "数据追溯性",
             "description": "记录并保持产品从原材料到最终交付的全生命周期历史、应用或位置的能力。", "level": None}
        ],
        "methods": [  # 合规方法
            {"name": "建立与运行供应商控制程序",
             "description": "制定书面程序，对供应商进行批准、评估、监督，并建立不合格品报告流程，确保供应链受控。",
             "content": "..."},
            {"name": "实施接收检验",
             "description": "对购入的零部件/产品进行文件审查和实物检验，验证其符合性声明与适航要求，确保可追溯性。",
             "content": "..."},
            {"name": "构建完整的质量记录体系",
             "description": "系统化地生成、收集、保存生产、检验、测试、维护及供应商管理的全流程记录，确保可审计和可追溯。",
             "content": "..."},
            {"name": "不合格品控制与纠正措施",
             "description": "识别、隔离、记录不合格品，分析根本原因并实施纠正措施，防止 recurrence。", "content": "..."}
        ]
    },
    7: {  # 第7章：积木式验证方法
        "id": 7,
        "title": "积木式验证方法",
        "description": "本章系统阐述了复合材料结构适航符合性验证中采用的“积木式”方法，包括其层级结构、核心原则、在静强度与疲劳损伤容限验证中的应用，以及相关的试验计划制定与审查关注点。",
        "prev_chapter": {"id": 6, "title": "第六章 质量体系与供应链适航监管"},
        "next_chapter": {"id": 8, "title": "第八章 疲劳与损伤容限要求"},
        "articles": [  # 相关法规
            {"code": "HB8605-2021 第5.3节",
             "title": "《飞机复合材料结构适航符合性验证通用要求》中对“积木式”方法的定义、要求和图示。",
             "content": "..."},
            {"code": "AC 20-107B 第7.b段", "title": "FAA对积木式验证方法的核心指导，阐述其原理、层级和应用。",
             "content": "..."},
            {"code": "AP-21-AA-2023-11R1",
             "title": "《型号合格审定程序》，规定了试验大纲编制、审批和制造符合性检查的流程。", "content": "..."},
            {"code": "CCAR-21-R4 第21.35条等", "title": "规定了申请人提交飞行试验数据和报告的要求。",
             "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "积木式方法 (BBA)",
             "description": "通过从简单试样到全尺寸部件的逐级、渐进式试验与分析，系统验证复合材料结构强度的工程方法。",
             "level": None},
            {"name": "试样/元件/典型结构件/部件",
             "description": "积木式方法的四个基本验证层级，分别解决材料性能、简单元件、结构细节和全尺寸系统集成问题。",
             "level": None},
            {"name": "损伤分类 (如BVID)",
             "description": "根据损伤的可检性和对结构剩余强度的影响对损伤进行分级，并规定不同的验证要求。",
             "level": None},
            {"name": "制造符合性检查",
             "description": "为确保试验产品构型、工艺与批准的设计数据一致而进行的检查，是试验数据有效性的前提。",
             "level": None},
            {"name": "符合性验证方法",
             "description": "表明适航条款符合性的十种途径（如试验、分析、检查）。“积木式”是支撑“试验”方法的具体策略。",
             "level": None}
        ],
        "methods": [  # 合规方法
            {"name": "实施积木式验证计划",
             "description": "规划和执行从试样到部件的分层级试验，系统获取统计数据和验证分析方法，以经济可靠地证明结构强度。",
             "content": "..."},
            {"name": "制定与报批试验大纲",
             "description": "依据AP-21程序，编制包含目的、步骤、判据等要素的详细试验大纲，并在试验前获得审查代表批准。",
             "content": "..."},
            {"name": "进行损伤威胁评估与分类",
             "description": "全面评估结构可能遭遇的损伤类型，并进行分类（如BVID），针对不同类别制定相应的验证和检查要求。",
             "content": "..."},
            {"name": "整合最终部件试验",
             "description": "在充分的低层级试验证据支持下，设计一个部件试验项目，以合理的加载顺序同时完成静强度、疲劳和损伤容限的最终验证。",
             "content": "..."}
        ]
    },
    8: {  # 第8章：疲劳与损伤容限要求
        "id": 8,
        "title": "疲劳与损伤容限要求",
        "description": "本章系统阐述了复合材料结构在疲劳、损伤容限方面的适航要求，包括损伤分类与验证、修理设计原则、修理方法验证、裂纹增长分析以及概率损伤容限评定程序，确保结构在服役期间的安全性。",
        "prev_chapter": {"id": 7, "title": "第七章 积木式验证方法"},
        "next_chapter": {"id": 9, "title": "第九章 结构设计审查与适航符合性分析"},
        "articles": [  # 相关法规
            {"code": "CCAR-25.571 / FAR 25.571", "title": "损伤容限和疲劳评定要求，本章分类验证要求的基础法规。",
             "content": "..."},
            {"code": "AC 20-107B 第8节",
             "title": "复合材料飞机结构的损伤容限和疲劳评定，详细阐述了损伤分类与验证要求。", "content": "..."},
            {"code": "HB8605-2021 相关章节",
             "title": "《飞机复合材料结构适航符合性验证通用要求》中关于损伤容限验证和修理验证的部分。",
             "content": "..."},
            {"code": "CCAR-25.305 / FAR 25.305", "title": "强度和变形要求，是静强度验证（包括修理后）的依据。",
             "content": "..."}
        ],
        "concepts": [  # 核心概念
            {"name": "损伤分类 (1-5类)",
             "description": "根据损伤的可检性、来源和威胁等级，将复合材料损伤分为五类，每类对应不同的剩余强度要求（极限载荷/限制载荷）和检查验证方法。",
             "level": None},
            {"name": "修理设计原则",
             "description": "在结构初始设计阶段为便于未来修理而考虑的通用性原则，如预留通道、优选螺接、考虑余量和采用组合构型。",
             "level": None},
            {"name": "修理多维验证",
             "description": "对修理方案不仅需验证静强度，还需综合验证其耐久性、刚度、气动外形、环境影响等多维度特性以满足适航要求。",
             "level": None},
            {"name": "裂纹增长行为",
             "description": "分为不增长、止裂增长和缓慢增长三种模式，直接影响检查间隔的确定和检查大纲的制定。",
             "level": None},
            {"name": "概率损伤容限评定",
             "description": "一种基于概率统计的方法，用于量化评估在结构的整个服役期内，意外损伤与载荷共同作用导致灾难性破坏的风险是否低于可接受目标。",
             "level": None}
        ],
        "methods": [  # 合规方法
            {"name": "损伤威胁评估与分类验证",
             "description": "系统识别结构可能遭遇的所有损伤威胁，并依据法规（如AC 20-107B）将其归入五类损伤，针对每类制定并执行相应的剩余强度验证试验和分析。",
             "content": "..."},
            {"name": "修理方案的多维度符合性验证",
             "description": "针对具体的修理设计，不仅进行静强度和疲劳试验，还需评估其对刚度、气动、防雷击、燃油密封等系统的影响，确保全面符合适航要求。",
             "content": "..."},
            {"name": "制定基于裂纹增长的检查大纲",
             "description": "根据裂纹增长特性（不增长/止裂/缓慢增长），确定合理的检查间隔、方法和范围，并将其制度化纳入飞机的持续适航维修计划。",
             "content": "..."},
            {"name": "实施概率损伤容限评定",
             "description": "通过建立“冲击能量-剩余强度”和“载荷-概率”曲线，计算损伤概率，并验证在用的检查程序能否在风险超出目标前以高概率检出损伤，以满足定量的安全目标。",
             "content": "..."}
        ]
    },
    9: {  # 第9章：结构设计审查与适航符合性分析
    "id": 9,
    "title": "结构设计审查与适航符合性分析",
    "description": "本章系统阐述了针对运输类飞机结构的适航符合性审查核心原则、结构分类审查的重点内容、具体的验证方法与流程，并明确了设计修改与维修时的符合性要求，确保结构在全生命周期内的安全性。",
    "prev_chapter": {"id": 8, "title": "第八章 疲劳与损伤容限要求"},  # 与HTML中导航链接对应
    "next_chapter": None,  # HTML中未显示“下一章”链接
    "articles": [  # 相关法规
        {"code": "FAR 25.571 / CCAR-25.571", "title": "损伤容限和疲劳评定，本章所有审查和验证工作的核心法规依据。", "content": "..."},
        {"code": "AC 25.571-1D", "title": "FAA关于运输类飞机损伤容限和疲劳评定的咨询通告，提供了可接受的符合性方法。", "content": "..."},
        {"code": "EASA AMC 25.571", "title": "欧洲航空安全局的可接受符合性方法，与FAA要求存在差异。", "content": "..."},
        {"code": "CCAR-25.305 / FAR 25.305", "title": "强度和变形要求，是静强度（包括剩余强度）验证的基础。", "content": "..."}
    ],
    "concepts": [  # 核心概念
        {"name": "主要结构件", "description": "对承受飞行、地面或增压载荷起重要作用，其完整性关乎飞机整体结构安全的构件。", "level": None},
        {"name": "疲劳关键结构", "description": "易发生疲劳裂纹且可能导致灾难性失效的结构，包括原始结构及维修改装后新增的易损部分。", "level": None},
        {"name": "损伤容限设计", "description": "要求结构在损伤（疲劳、腐蚀、意外）发生后，剩余结构仍能在定期检查间隔内承受规定的载荷。", "level": None},
        {"name": "广泛疲劳损伤 (WFD)", "description": "在结构中出现多处微小疲劳损伤，导致剩余强度下降到低于规定水平的状况。", "level": None},
        {"name": "适航限制章节 (ALS)", "description": "持续适航文件的一部分，强制性规定了检查阈值、间隔、改装或更换等限制，是符合性的最终证明文件。", "level": None}
    ],
    "methods": [  # 合规方法
        {"name": "结构分类与系统性审查", "description": "首先界定主要结构件、疲劳关键结构和WFD敏感结构，并针对不同类别，从损伤容限、疲劳、WFD防控、离散源损伤等维度进行系统性设计审查。", "content": "..."},
        {"name": "试验验证 (全尺寸/专项)", "description": "对WFD敏感结构进行代表实际运营的全尺寸疲劳试验，并通过裂纹扩展、剩余强度等专项试验支撑损伤容限和安全寿命分析。", "content": "..."},
        {"name": "分析验证 (确定性/概率性)", "description": "运用应力、疲劳寿命、裂纹扩展等确定性分析，或针对多载荷路径结构采用基于试验/运营数据的概率风险分析，证明结构符合性。", "content": "..."},
        {"name": "制定并纳入适航限制 (ALS)", "description": "将审查得出的强制性要求，如检查阈值/间隔、改装更换时限、有效性限制等，编制成文并纳入飞机的持续适航文件的适航限制章节。", "content": "..."}
    ]
}
}

# 初始化DeepSeek客户端
deepseek_client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL")
)


def build_system_prompt():
    """构建系统提示词，包含所有章节知识"""
    prompt = """你是一个专业的适航法规知识图谱助手，专门回答关于复合材料结构适航验证的问题。

## 知识库内容概览：
"""

    # 将所有章节知识构建到提示词中
    for chapter_id, chapter_info in fixed_chapter_data.items():
        prompt += f"""
### 第{chapter_id}章: {chapter_info['title']}
{chapter_info['description']}

相关法规：
{chr(10).join([f"- {a['code']}: {a['title']}" for a in chapter_info.get('articles', [])])}

核心概念：
{chr(10).join([f"- {c['name']}: {c['description']}" for c in chapter_info.get('concepts', [])])}
"""

        if 'methods' in chapter_info:
            prompt += f"""
合规方法：
{chr(10).join([f"- {m['name']}: {m['description']}" for m in chapter_info.get('methods', [])])}
"""
        prompt += "\n" + "=" * 50 + "\n"

    prompt += """
## 回答要求：
1. 基于上述知识库提供准确、专业的回答
2. 引用具体的章节、法规和概念
3. 如果问题超出知识范围，如实告知
4. 保持回答结构清晰、语言专业
"""

    return prompt

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/chapters')
def get_chapters():
    """获取所有章节"""
    query = """
    MATCH (c:Chapter)
    RETURN c.id as id, c.title as title, c.description as description
    ORDER BY c.id
    """
    results = kg.conn.execute_query(query)
    return jsonify(results)


@app.route('/chapter/<int:chapter_id>')
def get_chapter_detail(chapter_id):

    # 根据请求的章节ID返回对应的固定数据
    chapter_info = fixed_chapter_data.get(chapter_id)

    if not chapter_info:
        # 如果请求的章节ID不在固定数据中，返回404或空数据
        return jsonify({
            "chapter": {},
            "articles": [],
            "concepts": [],
            "prev_chapter": None,
            "next_chapter": None
        })

    # 构造与原始查询相同的返回数据结构
    data = {
        "chapter": {
            "id": chapter_info["id"],
            "title": chapter_info["title"],
            "description": chapter_info["description"]
        },
        "articles": chapter_info["articles"],
        "concepts": chapter_info["concepts"],
        "methods": chapter_info.get("methods", []),  # 添加此行，返回合规方法
        "prev_chapter": chapter_info["prev_chapter"],
        "next_chapter": chapter_info["next_chapter"]
    }

    return jsonify(data)


@app.route('/graph')
def get_graph_data():
    """获取图谱可视化数据"""
    nodes_query = """
        MATCH (n)
        RETURN 
          labels(n)[0] as labels,
          elementId(n) as id, 
          coalesce(n.title, n.name, n.code, n.description) as label,
          coalesce(n.description, n.content, '') as description,
          CASE 
            WHEN labels(n)[0] = 'Chapter' THEN 'chapter'
            WHEN labels(n)[0] = 'Article' THEN 'article'
            WHEN labels(n)[0] = 'Concept' THEN 'concept'
            WHEN labels(n)[0] = 'ComplianceMethod' THEN 'method'
            WHEN labels(n)[0] = 'BuildingBlock' THEN 'block'
            ELSE 'other'
          END as group
        """

    edges_query = """
        MATCH (a)-[r]->(b)
        RETURN 
          elementId(a) as source, 
          elementId(b) as target,
          type(r) as type,
          type(r) as label
        LIMIT 1000
        """

    nodes = kg.conn.execute_query(nodes_query)
    edges = kg.conn.execute_query(edges_query)

    # 格式化节点数据
    formatted_nodes = []
    for node in nodes:
        formatted_node = {
            "id": node["id"],  # 现在是字符串格式
            "label": node["label"][:20] + "..." if len(node.get("label", "")) > 20 else node.get("label", ""),
            "title": node.get("description", "")[:100] + "..." if len(node.get("description", "")) > 100 else node.get(
                "description", ""),
            "group": node["group"]
        }
        formatted_nodes.append(formatted_node)

    # 格式化边数据
    formatted_edges = []
    for edge in edges:
        formatted_edge = {
            "from": edge["source"],  # 现在也是字符串格式
            "to": edge["target"],  # 现在也是字符串格式
            "label": edge["type"],
            "arrows": "to"
        }
        formatted_edges.append(formatted_edge)

    print(f"节点数量: {len(nodes)}")
    print(f"边数量: {len(edges)}")

    # 打印前几个节点和边的示例
    if nodes:
        print("示例节点:", nodes[0])
    if edges:
        print("示例边:", edges[0])

    return jsonify({"nodes": formatted_nodes, "edges": formatted_edges})


@app.route('/chapter/<int:chapter_id>/detail')
def chapter_detail_page(chapter_id):
    """章节详细介绍页面"""
    # 获取章节详细信息
    query = f"""
    MATCH (c:Chapter {{id: {chapter_id}}})
    OPTIONAL MATCH (c)-[:REFERENCES]->(a:Article)
    OPTIONAL MATCH (c)-[:INCLUDES]->(con:Concept)
    OPTIONAL MATCH (c)-[:RELATED_TO]->(bb:BuildingBlock)
    OPTIONAL MATCH (c)-[:USES_METHOD]->(cm:ComplianceMethod)
    RETURN 
        c.id as id,
        c.title as title,
        c.description as description,
        c.content as content,
        collect(DISTINCT a) as articles,
        collect(DISTINCT con) as concepts,
        collect(DISTINCT bb) as building_blocks,
        collect(DISTINCT cm) as compliance_methods
    """

    result = kg.conn.execute_query(query)
    if not result:
        return "章节不存在", 404

    chapter_data = result[0]

    # 获取前后章节导航
    nav_query = f"""
    // 查找前一章
    MATCH (prev:Chapter)-[:NEXT_CHAPTER]->(c:Chapter {{id: {chapter_id}}})
    RETURN prev.id as id, prev.title as title, 'prev' as type
    UNION ALL
    // 查找后一章
    MATCH (c:Chapter {{id: {chapter_id}}})-[:NEXT_CHAPTER]->(next:Chapter)
    RETURN next.id as id, next.title as title, 'next' as type
    """

    nav_results = kg.conn.execute_query(nav_query)
    navigation = {
        "prev": None,
        "next": None
    }

    for nav in nav_results:
        if "prev_id" in nav:
            navigation["prev"] = {"id": nav["id"], "title": nav["title"]}
        if "next_id" in nav:
            navigation["next"] = {"id": nav["id"], "title": nav["title"]}

    return render_template(f'chapter/{chapter_id}/detail.html',
                           chapter=chapter_data,
                           navigation=navigation)


@app.route('/api/chapter/<int:chapter_id>/graph')
def chapter_subgraph(chapter_id):
    """获取章节子图数据（用于可视化）"""
    query = """
    MATCH (c:Chapter {id: $chapter_id})
    OPTIONAL MATCH (c)-[r]-(related)
    RETURN 
        c as chapter,
        collect(DISTINCT related) as related_nodes,
        collect(DISTINCT r) as relationships
    """

    result = kg.conn.execute_query(query, {"chapter_id": chapter_id})
    if result:
        return jsonify(result[0])
    return jsonify({})


@app.route('/search')
def search():
    """搜索功能 - 同时搜索Neo4j、固定数据字典 和 HTML详情页内容"""

    keyword = request.args.get('q', '').strip()

    if not keyword:
        return jsonify({"error": "请输入搜索关键词"})

    all_results = []
    keyword_lower = keyword.lower()


    # 1. 搜索固定数据字典 (FIXED_CHAPTER_DATA) - 保留原有逻辑
    for chapter_id, chapter_info in fixed_chapter_data.items():
        # 搜索章节标题和描述
        if (keyword_lower in chapter_info.get("title", "").lower() or
                keyword_lower in chapter_info.get("description", "").lower()):
            all_results.append({
                "type": "chapter",
                "title": f"第{chapter_id}章: {chapter_info['title']}",
                "description": chapter_info.get("description", ""),
                "id": chapter_id,
                "chapter_id": chapter_id
            })

        for article in chapter_info.get("articles", []):
            if (keyword_lower in article.get("code", "").lower() or
                    keyword_lower in article.get("title", "").lower()):
                all_results.append({
                    "type": "article",
                    "title": article.get("code", ""),
                    "description": article.get("title", ""),
                    "id": f"article_{chapter_id}_{article.get('code')}",
                    "chapter_id": chapter_id
                })

        for concept in chapter_info.get("concepts", []):
            if (keyword_lower in concept.get("name", "").lower() or
                keyword_lower in concept.get("description", "").lower()):
                all_results.append({
                    "type": "concept",
                    "title": concept.get("name", ""),
                    "description": concept.get("description", ""),
                    "id": f"concept_{chapter_id}_{concept.get('name')}",
                    "chapter_id": chapter_id
                })

        for method in chapter_info.get("methods", []):
            if (keyword_lower in method.get("name", "").lower() or
                keyword_lower in method.get("description", "").lower()):
                all_results.append({
                    "type": "method",
                    "title": method.get("name", ""),
                    "description": method.get("description", ""),
                    "id": f"method_{chapter_id}_{method.get('name')}",
                    "chapter_id": chapter_id
                })

    # 2. 新增：搜索所有章节的HTML详情页内容
    templates_base_path = os.path.join(os.path.dirname(__file__), 'templates', 'chapter')
    print("尝试搜索模板路径:", templates_base_path)
    print("该路径存在吗？", os.path.exists(templates_base_path))

    # 遍历templates/chapter目录下的所有子目录
    if os.path.exists(templates_base_path):
        for chapter_dir in os.listdir(templates_base_path):
            detail_path = os.path.join(templates_base_path, chapter_dir, 'detail.html')
            if os.path.isfile(detail_path):
                try:
                    with open(detail_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()

                    # 使用BeautifulSoup解析HTML，提取纯文本
                    soup = BeautifulSoup(html_content, 'html.parser')
                    # 移除脚本、样式等标签
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text_content = soup.get_text(separator=' ', strip=True)

                    # 检查关键词是否在文本内容中
                    if keyword_lower in text_content.lower():
                        # 尝试从路径或内容中获取章节ID
                        try:
                            ch_id = int(chapter_dir)  # 目录名即为章节ID
                        except ValueError:
                            continue

                        # 获取章节标题（从fixed_chapter_data或HTML中）
                        chapter_title = fixed_chapter_data.get(ch_id, {}).get('title', f'第{ch_id}章')

                        # 从文本内容中提取包含关键词的片段作为预览
                        preview_text = extract_snippet(text_content, keyword)

                        all_results.append({
                            "type": "html_content",
                            "title": f"第{ch_id}章: {chapter_title} (详情页内容)",
                            "description": preview_text[:150] + "..." if len(preview_text) > 150 else preview_text,
                            "id": f"html_chapter_{ch_id}",
                            "chapter_id": ch_id,
                            "preview": preview_text[:200]  # 更长的预览片段
                        })
                except Exception as e:
                    print(f"解析HTML文件 {detail_path} 时出错: {e}")
                    continue

    # 去重并限制结果数量
    seen = set()
    unique_results = []
    for r in all_results:
        # 使用(章节ID, 结果类型, 标题)作为唯一标识
        identifier = (r.get("chapter_id"), r.get("type"), r.get("title")[:50])
        if identifier not in seen:
            seen.add(identifier)
            unique_results.append(r)
        if len(unique_results) >= 30:  # 增加总结果数限制
            break

    return jsonify(unique_results)


@app.route('/concept/<path:name>')
def concept_page(name):
    if not re.match(r'^[\u4e00-\u9fff\w\-]+$', name):
        return "非法请求", 400

    html_path = os.path.join(os.path.dirname(__file__), 'concept', f"{name}.html")

    if not os.path.isfile(html_path):
        return f"概念「{name}」的页面尚未创建", 404

    return send_file(html_path, mimetype='text/html')


@app.route('/image_file/<path:name>')
def image_file_page(name):
    if not re.match(r'^[\u4e00-\u9fff\w\-]+$', name):
        return "非法请求", 400

    html_path = os.path.join(os.path.dirname(__file__), 'image_file', f"{name}.html")

    if not os.path.isfile(html_path):
        return f"概念「{name}」的页面尚未创建", 404

    return send_file(html_path, mimetype='text/html')

def extract_snippet(text, keyword, context_chars=100):
    """从文本中提取包含关键词的片段"""
    import re
    text_lower = text.lower()
    keyword_lower = keyword.lower()

    # 找到所有关键词出现的位置
    positions = [m.start() for m in re.finditer(re.escape(keyword_lower), text_lower)]

    if not positions:
        return text[:200]  # 如果没有匹配（理论上不会发生），返回开头部分

    # 取第一个匹配位置
    pos = positions[0]
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(keyword) + context_chars)

    snippet = text[start:end]
    # 高亮关键词（在前端处理，这里只返回文本）
    return snippet


@app.route('/visualize')
def visualize():
    """可视化页面"""
    return render_template('visualize.html')


@app.route('/api/chat', methods=['POST'])
def chat_with_deepseek():
    """智能问答接口"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()

        if not user_message:
            return jsonify({
                "success": False,
                "error": "请输入查询内容"
            })

        # 构建消息
        messages = [
            {
                "role": "system",
                "content": build_system_prompt()
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        # 调用DeepSeek API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",  # 或使用其他可用模型
            messages=messages,
            max_tokens=2000,
            temperature=0.7,
            stream=False
        )

        return jsonify({
            "success": True,
            "answer": response.choices[0].message.content
        })

    except Exception as e:
        print(f"DeepSeek API调用失败: {e}")
        return jsonify({
            "success": False,
            "error": f"智能查询失败: {str(e)}"
        })


@app.route('/api/chat/context', methods=['POST'])
def chat_with_context():
    """带章节上下文的智能问答"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        chapter_id = data.get('chapter_id')

        if not user_message:
            return jsonify({
                "success": False,
                "error": "请输入查询内容"
            })

        # 如果有章节ID，添加上下文
        context_prompt = build_system_prompt()
        if chapter_id and chapter_id in fixed_chapter_data:
            chapter_info = fixed_chapter_data[chapter_id]
            context_prompt += f"\n\n## 当前章节上下文（第{chapter_id}章）：\n"
            context_prompt += f"标题：{chapter_info['title']}\n"
            context_prompt += f"描述：{chapter_info['description']}\n"

        messages = [
            {
                "role": "system",
                "content": context_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        # 调用DeepSeek API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=2000,
            temperature=0.7
        )

        return jsonify({
            "success": True,
            "answer": response.choices[0].message.content
        })

    except Exception as e:
        print(f"带上下文的DeepSeek API调用失败: {e}")
        return jsonify({
            "success": False,
            "error": f"智能查询失败: {str(e)}"
        })

@app.route('/ai_query')
def ai_query_page():
    """智能查询页面"""
    return render_template('ai_query.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)