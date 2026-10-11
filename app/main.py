from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os

app = FastAPI(title="地质数据智能检索 Demo", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

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
NEO4J_PASSWORD = "geo12345"

EMBEDDING_MODEL = None


def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_embedding_model():
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        from fastembed import TextEmbedding

        EMBEDDING_MODEL = TextEmbedding(
            "BAAI/bge-small-zh-v1.5",
            cache_dir=os.getenv("FASTEMBED_CACHE_DIR", "/tmp/fastembed_cache"),
            local_files_only=os.getenv("FASTEMBED_LOCAL_FILES_ONLY", "true").lower()
            == "true",
        )
    return EMBEDDING_MODEL


app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)


@app.get("/")
def root_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/api")
def api_root():
    return {
        "message": "地质数据智能检索 API",
        "services": ["PostGIS", "Qdrant", "Neo4j"],
    }


@app.get("/stats")
def stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT count(*) as cnt FROM drillhole")
    drillholes = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM geochemistry")
    geochem = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM mining_area")
    mines = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM geo_document")
    docs = cur.fetchone()["cnt"]
    cur.close()
    conn.close()
    return {
        "drillholes": drillholes,
        "geochemistry_samples": geochem,
        "mining_areas": mines,
        "documents": docs,
    }


@app.get("/drillholes")
def list_drillholes(
    mine_area: str = Query(None, description="矿区名称筛选"),
    limit: int = Query(50, le=200),
):
    conn = get_db()
    cur = conn.cursor()
    if mine_area:
        cur.execute(
            """SELECT hole_id, project_name, elevation, depth, azimuth, dip,
                      lithology, ore_grade_li, ore_grade_ta, ore_grade_nb,
                      ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat
               FROM drillhole WHERE project_name LIKE %s LIMIT %s""",
            (f"%{mine_area}%", limit),
        )
    else:
        cur.execute(
            """SELECT hole_id, project_name, elevation, depth, azimuth, dip,
                      lithology, ore_grade_li, ore_grade_ta, ore_grade_nb,
                      ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat
               FROM drillhole LIMIT %s""",
            (limit,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"count": len(rows), "data": rows}


@app.get("/drillholes/nearby")
def nearby_drillholes(
    lng: float = Query(..., description="经度"),
    lat: float = Query(..., description="纬度"),
    radius_m: int = Query(5000, description="搜索半径(米)"),
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT hole_id, project_name, elevation, depth, lithology,
                  ore_grade_li, ore_grade_ta, ore_grade_nb,
                  ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat,
                  ST_Distance(location, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) as distance_m
           FROM drillhole
           WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
           ORDER BY distance_m LIMIT 50""",
        (lng, lat, lng, lat, radius_m),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        "center": {"lng": lng, "lat": lat},
        "radius_m": radius_m,
        "count": len(rows),
        "data": rows,
    }


@app.get("/mining-areas")
def list_mining_areas():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, name, area_km2, mine_type, status,
                  ST_AsGeoJSON(boundary) as boundary_geojson
           FROM mining_area"""
    )
    rows = cur.fetchall()
    for r in rows:
        r["boundary_geojson"] = json.loads(r["boundary_geojson"])
    cur.close()
    conn.close()
    return {"count": len(rows), "data": rows}


@app.get("/geochemistry")
def list_geochemistry(limit: int = Query(50, le=200)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT sample_id, au_ppb, ag_ppm, cu_ppm, li_ppm, w_ppm, sample_type,
                  ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat
           FROM geochemistry LIMIT %s""",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"count": len(rows), "data": rows}


@app.get("/documents")
def list_documents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, doc_type, mine_area, content, publish_date FROM geo_document"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"count": len(rows), "data": rows}


class VectorSearchRequest(BaseModel):
    query: str
    limit: int = 5


@app.post("/search/semantic")
def semantic_search(req: VectorSearchRequest):
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, prefer_grpc=True)

        if not client.collection_exists("geo_documents"):
            return {
                "query": req.query,
                "error": "向量集合未初始化",
                "hint": "请先运行 python init_qdrant_vectors.py",
            }

        model = get_embedding_model()
        query_vector = list(model.embed([req.query]))[0].tolist()

        results = client.search(
            collection_name="geo_documents",
            query_vector=query_vector,
            limit=req.limit,
        )

        return {
            "query": req.query,
            "mode": "semantic_vector_search",
            "model": "BAAI/bge-small-zh-v1.5",
            "results": [
                {
                    "score": round(r.score, 4),
                    "payload": {
                        "title": r.payload.get("title", ""),
                        "doc_type": r.payload.get("doc_type", ""),
                        "mine_area": r.payload.get("mine_area", ""),
                        "content": r.payload.get("content", ""),
                    },
                }
                for r in results
            ],
        }
    except ImportError:
        return {
            "query": req.query,
            "error": "fastembed 未安装",
            "hint": "请运行 pip install fastembed",
        }
    except Exception as e:
        return {
            "query": req.query,
            "error": str(e),
            "hint": "Qdrant 或 Embedding 服务可能未就绪",
        }


@app.get("/knowledge-graph/sample")
def knowledge_graph_sample():
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            entities_result = session.run(
                "MATCH (n) RETURN n.id as id, n.type as type, n.name as name LIMIT 50"
            )
            entities = [dict(r) for r in entities_result]

            relations_result = session.run(
                "MATCH (a)-[r]->(b) RETURN a.id as source, type(r) as relation, b.id as target LIMIT 50"
            )
            relations = [dict(r) for r in relations_result]

        driver.close()

        if entities:
            return {"entities": entities, "relations": relations}
    except Exception:
        pass

    return {
        "entities": [
            {"id": "yichun_tn", "type": "矿区", "name": "宜春钽铌矿"},
            {"id": "huaqiao", "type": "矿区", "name": "花桥锂矿"},
            {"id": "jiuling", "type": "矿区", "name": "九岭锂矿"},
            {"id": "li", "type": "矿种", "name": "锂云母"},
            {"id": "ta_nb", "type": "矿种", "name": "钽铌矿"},
            {"id": "granite_pegmatite", "type": "矿床类型", "name": "花岗伟晶岩型"},
            {"id": "albitization", "type": "蚀变", "name": "钠长石化"},
            {"id": "greisenization", "type": "蚀变", "name": "云英岩化"},
            {"id": "yanshanian", "type": "地层", "name": "燕山期花岗岩"},
        ],
        "relations": [
            {"source": "yichun_tn", "target": "li", "relation": "产出"},
            {"source": "yichun_tn", "target": "ta_nb", "relation": "产出"},
            {
                "source": "yichun_tn",
                "target": "granite_pegmatite",
                "relation": "矿床类型",
            },
            {"source": "yichun_tn", "target": "albitization", "relation": "蚀变"},
            {"source": "li", "target": "albitization", "relation": "伴生蚀变"},
            {"source": "li", "target": "greisenization", "relation": "伴生蚀变"},
            {"source": "huaqiao", "target": "li", "relation": "产出"},
            {"source": "jiuling", "target": "li", "relation": "产出"},
            {
                "source": "jiuling",
                "target": "granite_pegmatite",
                "relation": "矿床类型",
            },
            {
                "source": "yanshanian",
                "target": "granite_pegmatite",
                "relation": "成矿母岩",
            },
            {"source": "huaqiao", "target": "albitization", "relation": "蚀变"},
        ],
    }


@app.get("/knowledge-graph/query")
def knowledge_graph_query(
    entity: str = Query(..., description="实体ID或名称"),
    depth: int = Query(2, le=3, description="关系跳数"),
):
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            cypher = (
                "MATCH path = (a)-[*1.." + str(depth) + "]->(b) "
                "WHERE a.name CONTAINS $entity "
                "RETURN DISTINCT a.name as src_name, [l IN labels(a) WHERE l <> 'Entity' | l][0] as src_type, "
                "b.name as tgt_name, [l IN labels(b) WHERE l <> 'Entity' | l][0] as tgt_type, "
                "[r IN relationships(path) | type(r)] as rels"
            )
            result = session.run(cypher, entity=entity)
            paths = []
            seen_edges = set()
            nodes = {}
            for r in result:
                src_name = r["src_name"]
                tgt_name = r["tgt_name"]
                src_key = src_name
                tgt_key = tgt_name
                if src_key not in nodes:
                    nodes[src_key] = {
                        "id": src_key,
                        "name": src_name,
                        "type": r["src_type"] or "Unknown",
                    }
                if tgt_key not in nodes:
                    nodes[tgt_key] = {
                        "id": tgt_key,
                        "name": tgt_name,
                        "type": r["tgt_type"] or "Unknown",
                    }
                edge_key = f"{src_key}-{','.join(r['rels'])}-{tgt_key}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    paths.append(
                        {
                            "source": src_key,
                            "target": tgt_key,
                            "relations": r["rels"],
                        }
                    )
            driver.close()
            return {
                "query_entity": entity,
                "nodes": list(nodes.values()),
                "edges": paths,
            }
    except Exception as e:
        return {"query_entity": entity, "error": str(e)}


# =====================================================================
# LangGraph Agent 集成（追加于 2026-06-17）
# =====================================================================
# 把 LangGraph 编排的 ReAct Agent 作为子路由挂到 /agent 前缀下。
# 失败时不影响原有 7 个 REST 端点（用 try/except 软失败，便于排查）。
# Java 类比：在 SpringBoot 主类里 @Import 一个新的 @RestController。
try:
    from agent_routes import router as agent_router  # noqa: E402

    app.include_router(agent_router)
    print("[geo-api] /agent/* routes mounted via LangGraph")
except Exception as _agent_err:  # pragma: no cover
    # 让 LLM 依赖缺失或环境变量未配置时，主服务仍然能起来
    print(f"[geo-api] WARNING: agent router NOT mounted: {_agent_err}")
