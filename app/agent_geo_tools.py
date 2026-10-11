"""agent_geo_tools.py: LangChain @tool wrappers around geo-demo retrieval primitives.

Java 工程师视角速查：

@tool 装饰器 = LangChain 把普通 Python 函数变成 LLM 可见的 Tool 对象：
    1. 函数签名 + 类型注解 ── 翻译成 OpenAI Function Calling JSON Schema
    2. docstring ── 作为 description 传给 LLM
    3. 函数本身 ── 框架在 LLM 输出 ToolCall 时真去执行
    所以 docstring 写得清不清楚直接决定 LLM 调用准确率（这是这文件
    docstring 比代码长的根本原因）。

设计思路：进程内直连数据库，避免 main.py <-> agent 通过 HTTP 互相调用。
"""

from __future__ import annotations
import json
import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": 5432,
    "dbname": "geology",
    "user": "geo",
    "password": "geo123",
}
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = 6333
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "geo12345")


def _get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


_EMBED_MODEL = None


def _get_embedding_model():
    """懒加载 fastembed ONNX 模型；优先使用 Docker volume 持久化缓存，避免重建容器后重新联网等待。"""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from fastembed import TextEmbedding

        _EMBED_MODEL = TextEmbedding(
            "BAAI/bge-small-zh-v1.5",
            cache_dir=os.getenv("FASTEMBED_CACHE_DIR", "/tmp/fastembed_cache"),
            local_files_only=os.getenv("FASTEMBED_LOCAL_FILES_ONLY", "true").lower()
            == "true",
        )
    return _EMBED_MODEL


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@tool
def list_mining_areas() -> str:
    """列出江西省所有矿区的概览（名称、矿种、面积、状态、边界）。

    使用场景：
        - 用户问 "江西有哪些矿"、"矿区列表"、"列出所有矿区"
        - 通常作为多轮检索的第一步，让模型先掌握全局信息

    返回字段：
        id: 矿区主键
        name: 中文名（如 "宜春钽铌矿"、"龙南稀土矿"）
        mine_type: 矿种（"锂矿"、"钨矿"、"稀土" 等）
        status: 状态（"生产中"、"勘查中"、"资源枯竭"）
        area_km2: 面积平方公里
        boundary_geojson: 矿区 GeoJSON 多边形边界
    """
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, area_km2, mine_type, status, "
        "ST_AsGeoJSON(boundary) as boundary_geojson FROM mining_area"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    for r in rows:
        if r.get("boundary_geojson"):
            r["boundary_geojson"] = json.loads(r["boundary_geojson"])
    return _json({"count": len(rows), "data": rows})


@tool
def list_drillholes_by_mine(mine_area: Optional[str] = None, limit: int = 20) -> str:
    """按矿区名查询钻孔（深度、岩性、锂/钽/铌品位、坐标）。

    使用场景：
        - 用户提到具体矿区："宜春的钻孔"、"花桥锂矿钻探数据"
        - 想了解某矿区的勘探现状

    参数：
        mine_area: 矿区模糊匹配，如 "宜春"、"花桥"。传 None 返回所有钻孔
        limit: 最多返回条数（1~200，默认 20）

    返回字段：
        hole_id: 钻孔编号（ZK001 等）
        project_name: 所属项目
        elevation: 海拔（米）
        depth: 钻探深度（米）
        lithology: 岩性描述
        ore_grade_li: 锂品位（%）
        ore_grade_ta: 钽品位（ppm）
        ore_grade_nb: 铌品位（ppm）
        lng/lat: 经纬度
    """
    limit = max(1, min(int(limit), 200))
    conn = _get_db()
    cur = conn.cursor()
    sql_select = (
        "SELECT hole_id, project_name, elevation, depth, azimuth, dip, "
        "lithology, ore_grade_li, ore_grade_ta, ore_grade_nb, "
        "ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat "
        "FROM drillhole "
    )
    if mine_area:
        cur.execute(
            sql_select + "WHERE project_name LIKE %s LIMIT %s",
            (f"%{mine_area}%", limit),
        )
    else:
        cur.execute(sql_select + "LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _json({"count": len(rows), "data": rows})


@tool
def search_drillholes_nearby(lng: float, lat: float, radius_m: int = 5000) -> str:
    """以经纬度为中心、按半径搜索附近钻孔（PostGIS 空间查询）。

    使用场景：
        - 用户给出具体坐标
        - 想知道"某矿区周围 X 公里有什么钻孔"
        - 注意：如果只知道矿区名没坐标，先调 list_mining_areas 拿到边界中心，再用本工具

    参数：
        lng: 中心经度（江西范围约 113~119）
        lat: 中心纬度（江西范围约 24~30）
        radius_m: 搜索半径，米（1~100000，默认 5000）

    返回字段（按距离升序）：
        distance_m: 距中心点距离（米）
        hole_id, project_name, elevation, depth, lithology, ore_grade_*, lng, lat
    """
    radius_m = max(1, min(int(radius_m), 100000))
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT hole_id, project_name, elevation, depth, lithology, "
        "ore_grade_li, ore_grade_ta, ore_grade_nb, "
        "ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat, "
        "ST_Distance(location, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) as distance_m "
        "FROM drillhole "
        "WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s) "
        "ORDER BY distance_m LIMIT 50",
        (lng, lat, lng, lat, radius_m),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _json(
        {
            "center": {"lng": lng, "lat": lat},
            "radius_m": radius_m,
            "count": len(rows),
            "data": rows,
        }
    )


@tool
def query_geochemistry(limit: int = 30) -> str:
    """查询化探采样点元素含量（Au/Ag/Cu/Li/W）。

    使用场景：
        - 用户问 "化探数据"、"地化采样"、"元素含量"
        - 配合钻孔数据回答"勘探现状"类问题

    参数：
        limit: 最多返回采样点数（1~200，默认 30）

    返回字段：
        sample_id: 样品编号
        au_ppb: 金含量（ppb）
        ag_ppm: 银含量（ppm）
        cu_ppm: 铜含量（ppm）
        li_ppm: 锂含量（ppm）
        w_ppm: 钨含量（ppm）
        sample_type: 采样类型
        lng/lat: 采样点坐标
    """
    limit = max(1, min(int(limit), 200))
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT sample_id, au_ppb, ag_ppm, cu_ppm, li_ppm, w_ppm, sample_type, "
        "ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat "
        "FROM geochemistry LIMIT %s",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _json({"count": len(rows), "data": rows})


@tool
def semantic_search_documents(query: str, limit: int = 5) -> str:
    """对地质文献做语义检索（Qdrant + bge-small-zh 中文向量模型）。

    使用场景：
        - 自然语言问句："怎么从锂云母提锂"、"世界最大钨矿"、"花岗岩成矿条件"
        - 不是关键词匹配，是语义匹配
          （"提锂工艺"能找到"锂云母提取碳酸锂工艺研究"）
        - 用户问的概念在结构化数据里查不到时，用这个

    参数：
        query: 自然语言查询词
        limit: 返回前 N 条最相关文档（1~10，默认 5）

    返回字段：
        score: 相似度（0~1，越大越相关）
        title: 文档标题
        doc_type: 文档类型
        mine_area: 关联矿区
        content: 文档正文片段
    """
    from qdrant_client import QdrantClient

    limit = max(1, min(int(limit), 10))
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, prefer_grpc=True)
    if not client.collection_exists("geo_documents"):
        return _json(
            {
                "error": "Qdrant collection not initialized",
                "hint": "run init_qdrant_vectors.py",
            }
        )
    model = _get_embedding_model()
    query_vector = list(model.embed([query]))[0].tolist()
    results = client.search(
        collection_name="geo_documents",
        query_vector=query_vector,
        limit=limit,
    )
    return _json(
        {
            "query": query,
            "results": [
                {
                    "score": round(r.score, 4),
                    "title": r.payload.get("title", ""),
                    "doc_type": r.payload.get("doc_type", ""),
                    "mine_area": r.payload.get("mine_area", ""),
                    "content": r.payload.get("content", ""),
                }
                for r in results
            ],
        }
    )


@tool
def query_knowledge_graph(entity: str, depth: int = 2) -> str:
    """在 Neo4j 知识图谱里查询某实体的多跳关联（矿物-矿床-蚀变-岩性）。

    使用场景：
        - 用户问 "X 跟啥相关"、"X 的成矿条件"、"X 伴生啥矿物"
        - 探索矿区/矿物之间的间接关系（2 跳能发现 "矿区-矿物-工艺" 这种链）

    参数：
        entity: 实体名或 ID 模糊匹配，如 "宜春"、"锂云母"、"花岗岩"
        depth: 关系跳数（1~3，默认 2）

    返回字段：
        nodes: 节点列表，每项含 id、name、type
        edges: 边列表，每项含 source、target、relations（关系链路）
    """
    from neo4j import GraphDatabase

    depth = max(1, min(int(depth), 3))
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            cypher = (
                "MATCH path = (a)-[*1.." + str(depth) + "]->(b) "
                "WHERE a.name CONTAINS $entity "
                "RETURN DISTINCT a.name as src_name, "
                "[l IN labels(a) WHERE l <> 'Entity' | l][0] as src_type, "
                "b.name as tgt_name, "
                "[l IN labels(b) WHERE l <> 'Entity' | l][0] as tgt_type, "
                "[r IN relationships(path) | type(r)] as rels"
            )
            result = session.run(cypher, entity=entity)
            nodes = {}
            edges = []
            seen = set()
            for r in result:
                src, tgt = r["src_name"], r["tgt_name"]
                if src not in nodes:
                    nodes[src] = {
                        "id": src,
                        "name": src,
                        "type": r["src_type"] or "Unknown",
                    }
                if tgt not in nodes:
                    nodes[tgt] = {
                        "id": tgt,
                        "name": tgt,
                        "type": r["tgt_type"] or "Unknown",
                    }
                edge_key = f"{src}-{','.join(r['rels'])}-{tgt}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({"source": src, "target": tgt, "relations": r["rels"]})
        driver.close()
        return _json(
            {
                "query_entity": entity,
                "depth": depth,
                "nodes": list(nodes.values()),
                "edges": edges,
            }
        )
    except Exception as e:
        return _json({"query_entity": entity, "error": str(e)})


# ────────────────────────────────────────────────────────────────────
# Agent 工具清单（导出给 LangGraph 使用）
# ────────────────────────────────────────────────────────────────────
ALL_TOOLS = [
    list_mining_areas,
    list_drillholes_by_mine,
    search_drillholes_nearby,
    query_geochemistry,
    semantic_search_documents,
    query_knowledge_graph,
]
