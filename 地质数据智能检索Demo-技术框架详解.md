# 地质数据智能检索 Demo — 技术框架详解

---

## 一、项目概述

### 1.1 这是什么？

一个地质数据智能检索系统，演示如何用 **3种不同类型的数据库** 协同工作，实现地质数据的"多模态检索"：

| 能力 | 实现方式 | 说明 |
|------|---------|------|
| 空间检索（按地理位置搜索） | PostGIS | PostgreSQL 地理空间扩展，支持球面距离计算 |
| 语义检索（按意思搜索，不是关键词） | Qdrant 向量数据库 | 基于向量相似度，超越关键词匹配 |
| 知识图谱（实体关系推理） | Neo4j 图数据库 | 用图结构表达实体及其多跳关系 |

### 1.2 项目目标

围绕地质数据的三个特点，搭建对应的数据能力：

1. **空间数据**：用 PostGIS 存储和检索钻孔、化探点、矿区边界等空间对象
2. **文档数据**：用 Qdrant 实现基于语义的地质文献检索
3. **实体关系**：用 Neo4j 表达矿区、矿种、蚀变、矿床类型之间的多跳关联

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────┐
│                    浏览器 (index.html)                     │
│         Leaflet地图 + 表格 + 搜索框 + 知识图谱展示          │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP REST API
                           ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI 后端 (main.py)                       │
│                                                          │
│  /stats            → 统计概览                             │
│  /drillholes       → 钻孔列表查询                         │
│  /drillholes/nearby→ 空间近邻查询（调用PostGIS）            │
│  /mining-areas     → 矿区边界查询                         │
│  /geochemistry     → 化探数据查询                         │
│  /documents        → 地质文档列表                         │
│  /search/semantic  → 语义检索（调用Qdrant）                │
│  /knowledge-graph  → 知识图谱查询（调用Neo4j）              │
└───────┬──────────────┬──────────────┬───────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  PostGIS     │ │   Qdrant     │ │   Neo4j      │
│  (空间数据库)  │ │ (向量数据库)  │ │ (图数据库)    │
│  Port: 5432  │ │ Port: 6333   │ │ Port: 7687   │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## 三、三大核心数据库详解

### 3.1 PostGIS — 空间数据库

#### 是什么？

PostGIS 是 PostgreSQL 的地理空间扩展，相当于给普通数据库加了"地图能力"。

普通数据库里存经纬度时，查询用 `WHERE lng BETWEEN ? AND ? AND lat BETWEEN ? AND ?`，但这只能做矩形范围过滤，算不了真实球面距离（地球是圆的）。PostGIS 原生支持球面计算。

#### 核心概念

| PostGIS 概念 | 解释 | SQL 示例 |
|-------------|------|---------|
| `geography(POINT, 4326)` | 地理坐标点类型，4326是WGS84坐标系（GPS用的） | `location geography(POINT, 4326)` |
| `ST_GeomFromText('POINT(114.38 27.88)', 4326)` | 把文本坐标转成空间对象 | 插入数据时用 |
| `ST_DWithin(loc1, loc2, distance)` | 判断两个点是否在指定距离内 | **这是空间检索的核心函数** |
| `ST_Distance(loc1, loc2)` | 计算两个点之间的球面距离（米） | 排序用 |
| `ST_X(location::geometry)` | 从空间对象提取经度 | 查询结果展示用 |
| `ST_Y(location::geometry)` | 从空间对象提取纬度 | 查询结果展示用 |
| `GiST索引` | 空间索引，加速地理查询 | `CREATE INDEX ... USING GIST(location)` |

#### 本项目的数据表设计

```sql
-- 钻孔表：存储每个钻孔的位置、深度、岩性、品位等
CREATE TABLE drillhole (
    id SERIAL PRIMARY KEY,              -- 自增主键（相当于 BIGINT AUTO_INCREMENT）
    hole_id VARCHAR(50) NOT NULL,       -- 钻孔编号，如 ZK001
    project_name VARCHAR(100),          -- 项目名称
    location geography(POINT, 4326),    -- ★ 空间坐标点（PostGIS 核心字段）
    elevation NUMERIC(8,2),             -- 孔口标高(m)
    depth NUMERIC(8,2),                 -- 孔深(m)
    azimuth NUMERIC(6,2),               -- 方位角(°)
    dip NUMERIC(6,2),                   -- 倾角(°)
    lithology TEXT,                     -- 岩性描述
    ore_grade_li NUMERIC(6,4),          -- Li₂O 品位(%)
    ore_grade_ta NUMERIC(6,4),          -- Ta₂O₅ 品位(%)
    ore_grade_nb NUMERIC(6,4),          -- Nb₂O₅ 品位(%)
    created_at TIMESTAMP DEFAULT NOW()
);

-- 矿区边界表：存储矿区范围（多边形）
CREATE TABLE mining_area (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    boundary geography(POLYGON, 4326),  -- ★ 空间多边形（矿区范围）
    area_km2 NUMERIC(10,2),             -- 面积(km²)
    mine_type VARCHAR(50),              -- 矿种类型
    status VARCHAR(30),                 -- 开发状态
    created_at TIMESTAMP DEFAULT NOW()
);

-- 化探数据表：土壤/岩石化学分析结果
CREATE TABLE geochemistry (
    id SERIAL PRIMARY KEY,
    sample_id VARCHAR(50) NOT NULL,
    location geography(POINT, 4326),    -- ★ 采样点坐标
    au_ppb NUMERIC(8,2),                -- 金含量(ppb)
    ag_ppm NUMERIC(8,2),                -- 银含量(ppm)
    cu_ppm NUMERIC(8,2),                -- 铜含量(ppm)
    li_ppm NUMERIC(8,2),                -- 锂含量(ppm)
    w_ppm NUMERIC(8,2),                 -- 钨含量(ppm)
    sample_type VARCHAR(30),            -- 样品类型（土壤/岩石）
    created_at TIMESTAMP DEFAULT NOW()
);

-- 地质文档表：勘查报告、储量报告等文本数据
CREATE TABLE geo_document (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    doc_type VARCHAR(50),               -- 文档类型
    mine_area VARCHAR(100),             -- 所属矿区
    content TEXT,                        -- 文档正文
    publish_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ★ 空间索引：这是 PostGIS 查询性能的关键
CREATE INDEX idx_drillhole_location ON drillhole USING GIST(location);
CREATE INDEX idx_geochemistry_location ON geochemistry USING GIST(location);
CREATE INDEX idx_mining_area_boundary ON mining_area USING GIST(boundary);
```

#### 空间检索的核心 SQL

```sql
-- 查找某坐标附近 N 米内的所有钻孔，并按距离排序
-- 这条 SQL 等价于"查找宜春市区10公里内所有钻孔"
SELECT hole_id, project_name, depth, lithology, ore_grade_li,
       ST_X(location::geometry) as lng,
       ST_Y(location::geometry) as lat,
       ST_Distance(
           location,
           ST_SetSRID(ST_MakePoint(114.40, 27.90), 4326)::geography
       ) as distance_m
FROM drillhole
WHERE ST_DWithin(
    location,
    ST_SetSRID(ST_MakePoint(114.40, 27.90), 4326)::geography,
    50000    -- 50公里半径
)
ORDER BY distance_m
LIMIT 50;
```

**逐行解释**：
- `ST_MakePoint(114.40, 27.90)` — 创建一个坐标点
- `ST_SetSRID(..., 4326)` — 指定坐标系为 WGS84
- `::geography` — 转成地理类型（球面计算，单位是米）
- `ST_DWithin(loc1, loc2, 50000)` — 判断两个点是否在 50km 内
- `ST_Distance(loc1, loc2)` — 计算精确球面距离

### 3.2 Qdrant — 向量数据库

#### 是什么？

Qdrant 是专门存储和检索**向量**的数据库。向量是 AI 模型把文本/图片转成的数字数组。

```
传统搜索（Elasticsearch/MySQL LIKE）：
  用户搜 "锂矿成矿条件"
  → 精确匹配 "锂矿" 和 "成矿条件" 这几个字
  → 找不到 "含锂矿床形成机理"（因为字不一样）

语义搜索（Qdrant）：
  用户搜 "锂矿成矿条件"
  → AI模型把这句话变成一个512维向量 [0.12, -0.34, 0.56, ...]
  → 在数据库中找向量最接近的文档
  → 能找到 "含锂矿床形成机理"（因为意思接近，向量就接近）
```

#### 核心概念

| 概念 | 解释 | 类比 |
|------|------|------|
| **向量 (Vector)** | 一组浮点数，如 `[0.12, -0.34, 0.56, ...]`，表示文本的"语义坐标" | 没有直接类比，可以理解为给每段文字一个GPS坐标，意思相近的坐标就相近 |
| **Embedding 模型** | 把文本转成向量的 AI 模型 | 相当于一个"文本→坐标"的转换器 |
| **Collection** | 向量的集合，类似数据库的表 | MySQL 的 Table |
| **Point** | 一条向量记录（id + vector + payload） | MySQL 的一行记录 |
| **余弦相似度 (Cosine Similarity)** | 衡量两个向量相似程度的算法，值0~1 | 类比两栋楼的距离，但用角度而不是米来衡量 |
| **BAAI/bge-small-zh-v1.5** | 中文文本 embedding 模型，512维 | 没有类比，这是一个预训练AI模型 |

#### 向量搜索的工作流程

```
1. 入库阶段（离线）：
   "宜春钽铌矿位于江西省宜春市..."
        │
        ▼  Embedding 模型编码
   [0.12, -0.34, 0.56, 0.78, ...]  (512个浮点数)
        │
        ▼  存入 Qdrant
   Point { id=1, vector=[...], payload={title, content, ...} }

2. 查询阶段（在线）：
   用户输入 "锂矿成矿条件"
        │
        ▼  Embedding 模型编码（同一个模型）
   [0.11, -0.32, 0.54, 0.77, ...]  (512个浮点数)
        │
        ▼  Qdrant 搜索最相似的向量
   返回: {id=1, score=0.92, payload={title:"宜春钽铌矿..."}}
```

#### 本项目的 Qdrant 使用

```python
# 创建集合（类似 CREATE TABLE）
client.create_collection(
    collection_name="geo_documents",
    vectors_config=models.VectorParams(
        size=32,                    # 向量维度（演示用32维，生产用512维）
        distance=models.Distance.COSINE,  # 用余弦相似度衡量距离
    ),
)

# 插入向量（类似 INSERT INTO）
client.upsert(
    collection_name="geo_documents",
    points=[
        models.PointStruct(
            id=1,
            vector=[0.12, -0.34, ...],   # 32维向量
            payload={                      # 附加元数据
                "title": "宜春钽铌矿...",
                "doc_type": "研究报告",
                "content": "宜春钽铌矿位于..."
            },
        )
    ],
)

# 搜索（类似 SELECT ... ORDER BY similarity DESC LIMIT 5）
results = client.search(
    collection_name="geo_documents",
    query_vector=[0.11, -0.32, ...],   # 用户查询的向量
    limit=5,
)
# 返回: [{id:1, score:0.92, payload:{...}}, ...]
```

### 3.3 Neo4j — 图数据库

#### 是什么？

Neo4j 是存储"实体+关系"的图数据库。传统数据库存"表格"，图数据库存"网络"。

```
关系数据库（MySQL/PostgreSQL）：
  矿区表:  id=1, name="宜春钽铌矿"
  矿种表:  id=1, name="锂云母"
  关系表:  mine_id=1, mineral_id=1, relation="产出"
  → 查"宜春钽铌矿产出什么矿种"需要 JOIN 3张表

图数据库（Neo4j）：
  节点:   (宜春钽铌矿) --[产出]--> (锂云母)
  → 一条语句直接查出来，还能做多跳推理
```

#### 核心概念

| 概念 | 解释 | Cypher 语法 |
|------|------|------------|
| **Node（节点）** | 实体，如"宜春钽铌矿"、"锂云母" | `(n:Entity {name: "宜春钽铌矿"})` |
| **Relationship（关系）** | 节点之间的有向边，如"产出" | `()-[:产出]->()` |
| **Label（标签）** | 节点的类型，如"矿区"、"矿种" | `:Entity` |
| **Property（属性）** | 节点/关系的键值对 | `{id: "yichun_tn", type: "矿区"}` |
| **Cypher** | Neo4j 的查询语言 | `MATCH (n) RETURN n` |

#### Cypher vs SQL 对比

| 操作 | SQL | Cypher |
|------|-----|--------|
| 查所有实体 | `SELECT * FROM entity` | `MATCH (n) RETURN n` |
| 查某矿区产出的矿种 | `SELECT m.name FROM entity e JOIN relation r ON e.id=r.src_id JOIN entity m ON r.tgt_id=m.id WHERE e.name='宜春钽铌矿' AND r.type='产出'` | `MATCH (a:Entity {name:"宜春钽铌矿"})-[:产出]->(b:Entity) RETURN b.name` |
| 查两跳关系（矿区→矿种→蚀变） | 需要再 JOIN 一次 | `MATCH (a)-[:产出]->(b)-[:伴生蚀变]->(c) RETURN a,c` |

#### 本项目的知识图谱数据

```
实体 (9个):
  矿区: 宜春钽铌矿、花桥锂矿、九岭锂矿
  矿种: 锂云母、钽铌矿
  矿床类型: 花岗伟晶岩型
  蚀变: 钠长石化、云英岩化
  地层: 燕山期花岗岩

关系 (11条):
  宜春钽铌矿 --[产出]--> 锂云母
  宜春钽铌矿 --[产出]--> 钽铌矿
  宜春钽铌矿 --[矿床类型]--> 花岗伟晶岩型
  宜春钽铌矿 --[蚀变]--> 钠长石化
  锂云母 --[伴生蚀变]--> 钠长石化
  锂云母 --[伴生蚀变]--> 云英岩化
  花桥锂矿 --[产出]--> 锂云母
  九岭锂矿 --[产出]--> 锂云母
  九岭锂矿 --[矿床类型]--> 花岗伟晶岩型
  燕山期花岗岩 --[成矿母岩]--> 花岗伟晶岩型
  花桥锂矿 --[蚀变]--> 钠长石化
```

---

## 四、后端 API 详解

### 4.1 技术选型

| 考量 | 说明 |
|------|------|
| **AI 生态** | fastembed、qdrant-client、neo4j driver 在 Python 生态最成熟 |
| **快速原型** | FastAPI 简洁轻量，几行代码即可暴露 REST API |
| **生产部署** | 可用 Gunicorn + Uvicorn 多进程部署，也可置于 Nginx 反向代理之后 |

### 4.2 API 端点一览

| 端点 | 方法 | 功能 | 调用的数据库 |
|------|------|------|------------|
| `/` | GET | 返回前端页面 | 无 |
| `/stats` | GET | 统计概览 | PostGIS |
| `/drillholes` | GET | 钻孔列表 | PostGIS |
| `/drillholes/nearby` | GET | 空间近邻查询 | PostGIS (ST_DWithin) |
| `/mining-areas` | GET | 矿区边界 | PostGIS (ST_AsGeoJSON) |
| `/geochemistry` | GET | 化探数据 | PostGIS |
| `/documents` | GET | 地质文档列表 | PostGIS |
| `/search/semantic` | POST | 语义检索 | Qdrant |
| `/knowledge-graph/sample` | GET | 知识图谱 | Neo4j (Cypher) |

### 4.3 核心 API 代码解读

#### 空间近邻查询（最重要的 API）

```python
@app.get("/drillholes/nearby")
def nearby_drillholes(
    lng: float = Query(..., description="经度"),     # 相当于 @RequestParam
    lat: float = Query(..., description="纬度"),
    radius_m: int = Query(5000, description="搜索半径(米)"),  # 默认5km
):
    conn = get_db()                                    # 相当于 dataSource.getConnection()
    cur = conn.cursor()                                # 相当于 Statement
    cur.execute(
        """SELECT hole_id, project_name, depth, lithology,
                  ore_grade_li, ore_grade_ta, ore_grade_nb,
                  ST_X(location::geometry) as lng,          # 提取经度
                  ST_Y(location::geometry) as lat,           # 提取纬度
                  ST_Distance(                               # 计算距离(米)
                      location,
                      ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography
                  ) as distance_m
           FROM drillhole
           WHERE ST_DWithin(                                # 空间过滤
                      location,
                      ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                      %s                                    # 半径
                   )
           ORDER BY distance_m LIMIT 50""",
        (lng, lat, lng, lat, radius_m),                    # 参数绑定（防SQL注入）
    )
    rows = cur.fetchall()                                   # 相当于 ResultSet → List<Map>
    cur.close()
    conn.close()                                            # ⚠️ 生产环境应用连接池
    return {"center": {"lng": lng, "lat": lat}, "radius_m": radius_m,
            "count": len(rows), "data": rows}
```

#### 语义检索 API

```python
@app.post("/search/semantic")
def semantic_search(req: VectorSearchRequest):       # req 相当于 @RequestBody
    from qdrant_client import QdrantClient
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, prefer_grpc=True)

    # 从 Qdrant 中获取所有向量点
    points, _ = client.scroll(
        collection_name="geo_documents",
        limit=req.limit,
        with_payload=True,
    )

    # 用关键词匹配计算相似度（Demo 简化方案）
    # 生产环境应该用 Embedding 模型计算查询向量，然后用 client.search() 做向量相似度检索
    keywords = [kw for kw in req.query.replace("的", " ").split() if len(kw) > 1]
    results = []
    for p in points:
        payload = p.payload or {}
        text = f"{payload.get('title', '')} {payload.get('content', '')}"
        score = sum(1.0 for kw in keywords if kw in text) / max(len(keywords), 1)
        results.append({"score": round(score, 3), "payload": payload})

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"query": req.query, "mode": "keyword_weighted_search_in_vector_db",
            "results": results}
```

#### 知识图谱 API

```python
@app.get("/knowledge-graph/sample")
def knowledge_graph_sample():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        # Cypher 查询：获取所有实体
        entities_result = session.run(
            "MATCH (n) RETURN n.id as id, n.type as type, n.name as name LIMIT 50"
        )
        entities = [dict(r) for r in entities_result]

        # Cypher 查询：获取所有关系
        relations_result = session.run(
            "MATCH (a)-[r]->(b) RETURN a.id as source, type(r) as relation, b.id as target LIMIT 50"
        )
        relations = [dict(r) for r in relations_result]

    driver.close()
    return {"entities": entities, "relations": relations}
```

---

## 五、前端页面说明

### 5.1 技术栈

- 纯 HTML/CSS/JS，无框架
- **Leaflet.js**：开源地图库（类似百度地图 JS API）
- 通过 `fetch()` 调用后端 API

### 5.2 页面功能模块

| 模块 | 功能 | 数据来源 |
|------|------|---------|
| 统计概览 | 4个数据卡片（钻孔数、化探样品、矿区、文档） | `/stats` |
| 矿区地图 | Leaflet 地图上显示矿区边界（蓝色多边形）和钻孔（橙色圆点） | `/drillholes` + `/mining-areas` |
| 钻孔数据表 | 钻孔列表，显示孔号、项目、深度、岩性、Li品位 | `/drillholes` |
| 语义检索 | 输入地质问题，返回语义匹配的文档 | `/search/semantic` |
| 空间检索 | 输入坐标和半径，查找附近钻孔 | `/drillholes/nearby` |
| 知识图谱 | 显示实体卡片和关系连线 | `/knowledge-graph/sample` |

---

## 六、Docker 部署架构

### 6.1 docker-compose 配置解读

```yaml
services:
  geo-postgres:                         # PostGIS 空间数据库
    image: postgis/postgis:16-3.4       # PostgreSQL 16 + PostGIS 3.4
    environment:
      POSTGRES_USER: geo                # 数据库用户名
      POSTGRES_PASSWORD: geo123         # 数据库密码
      POSTGRES_DB: geology              # 数据库名
    ports:
      - "5432:5432"                     # 宿主机5432→容器5432
    volumes:
      - pgdata:/var/lib/postgresql/data         # 数据持久化
      - ./init_sql:/docker-entrypoint-initdb.d  # ★ 首次启动自动执行SQL
    mem_limit: 1g                       # 内存限制（4GB服务器要省着用）

  qdrant:                               # 向量数据库
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"                     # REST API 端口
      - "6334:6334"                     # gRPC 端口
    volumes:
      - qdrant_data:/qdrant/storage
    mem_limit: 512m

  neo4j:                                # 图数据库
    image: neo4j:5-community            # 社区版（免费）
    environment:
      NEO4J_AUTH: neo4j/geo12345        # 用户名/密码
      NEO4J_PLUGINS: '["apoc"]'         # APOC 扩展插件
      NEO4J_server_memory_heap_initial__size: 256m    # JVM 堆初始大小
      NEO4J_server_memory_heap_max__size: 512m        # JVM 堆最大值
    ports:
      - "7474:7474"                     # Web 管理界面
      - "7687:7687"                     # Bolt 协议（二进制通信）
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    mem_limit: 1g
```

### 6.2 关键概念解释

| 概念 | 解释 |
|------|------|
| `docker-entrypoint-initdb.d` | PostgreSQL 的特殊目录，容器首次启动时会自动执行里面的 `.sql` 文件 |
| `volumes` | Docker 数据卷，容器删了数据不丢（相当于给容器挂了一个外部硬盘） |
| `mem_limit` | 容器内存上限，3个数据库总共限制 2.5GB，给宿主机留 1.5GB |
| `bolt://` | Neo4j 的二进制通信协议，比 HTTP 快，类似 MySQL 的原生协议 |
| `apoc` | Neo4j 的扩展存储过程库，提供很多实用函数 |

---

## 七、项目文件结构

```
geo-demo/
├── docker-compose-db.yml        # Docker Compose 配置（3个数据库）
├── init_sql/
│   └── 01_init_geology.sql      # PostGIS 建表+示例数据（首次启动自动执行）
└── app/
    ├── main.py                  # FastAPI 后端（8个API端点）
    ├── requirements.txt         # Python 依赖（无 PyTorch，轻量版）
    ├── init_qdrant_vectors.py   # 向量数据初始化脚本
    ├── init_neo4j.py            # 知识图谱初始化脚本
    └── static/
        └── index.html           # 前端页面
```

---

## 八、数据初始化脚本详解

### 8.1 PostGIS 数据初始化

**自动执行**：`01_init_geology.sql` 放在 `./init_sql/` 目录下，Docker 挂载到容器的 `docker-entrypoint-initdb.d`，PostgreSQL 首次启动时自动执行。

**数据内容**（宜春地区示例）：

| 表 | 数据量 | 说明 |
|----|-------|------|
| drillhole | 7条 | 3个矿区的钻孔数据，含坐标、深度、品位 |
| mining_area | 3条 | 宜春钽铌矿、花桥锂矿、九岭锂矿 |
| geochemistry | 5条 | 化探样品，含 Au/Ag/Cu/Li/W 含量 |
| geo_document | 3条 | 地质勘查报告、储量报告、勘探报告 |

### 8.2 Qdrant 向量初始化

**手动执行**：`python3 init_qdrant_vectors.py`

流程：
1. 连接 Qdrant
2. 创建 collection（向量维度=32，余弦距离）
3. 对3个文档用 SHA256 生成确定性伪随机向量（生产环境应用 BAAI/bge-small-zh-v1.5 编码）
4. 上传到 Qdrant

### 8.3 Neo4j 知识图谱初始化

**手动执行**：`python3 init_neo4j.py`

流程：
1. 连接 Neo4j
2. 清空旧数据
3. 创建9个实体节点（矿区、矿种、矿床类型、蚀变、地层）
4. 创建11条关系边（产出、矿床类型、蚀变、伴生蚀变、成矿母岩）

---

## 九、生产环境 vs Demo 差异

| 方面 | Demo | 生产环境 |
|------|------|---------|
| 向量编码 | SHA256伪随机向量 | BAAI/bge-small-zh-v1.5 真实 embedding |
| 语义搜索 | 关键词匹配后备 | 真正的向量相似度检索 |
| 数据库连接 | 每次新建连接 | 连接池（如 SQLAlchemy async pool） |
| API 部署 | uvicorn 单进程 | Gunicorn + 多 worker + Nginx 反向代理 |
| 认证鉴权 | 无 | JWT / OAuth2 |
| 向量编码服务 | 无（预计算） | 独立 Embedding Service（FastAPI + sentence-transformers） |
| 前端 | 纯HTML | React/Vue + ECharts + D3.js（图谱可视化） |
| 数据量 | 3文档/7钻孔/9实体 | 万级文档/百万级钻孔/千级实体 |

---

## 十、技术栈速查表

| 技术 | 版本 | 用途 | 官网 |
|------|------|------|------|
| PostgreSQL | 16 | 关系数据库 | postgresql.org |
| PostGIS | 3.4 | PostgreSQL空间扩展 | postgis.net |
| Qdrant | latest | 向量数据库 | qdrant.tech |
| Neo4j | 5-community | 图数据库 | neo4j.com |
| Python | 3.12 | 后端语言 | python.org |
| FastAPI | 0.115 | Web框架 | fastapi.tiangolo.com |
| Uvicorn | 0.30 | ASGI服务器 | uvicorn.org |
| psycopg2 | 2.9 | PostgreSQL驱动 | pypi.org/project/psycopg2 |
| qdrant-client | 1.11 | Qdrant Python SDK | pypi.org/project/qdrant-client |
| neo4j (Python) | 5.25 | Neo4j Python Driver | pypi.org/project/neo4j |
| Leaflet | 1.9 | 前端地图库 | leafletjs.com |
| Docker | - | 容器化 | docker.com |
| Docker Compose | - | 多容器编排 | docs.docker.com/compose |

---

## 十一、快速操作手册

### 启动服务

```bash
# 1. 启动3个数据库
cd <项目根目录>
docker compose -f docker-compose-db.yml up -d

# 2. 等待 PostGIS 就绪（约10秒）
docker logs geo-postgres 2>&1 | tail -3

# 3. 初始化 Qdrant 向量
cd app && python3 init_qdrant_vectors.py

# 4. 初始化 Neo4j 知识图谱
python3 init_neo4j.py

# 5. 启动 API
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 &

# 6. 验证
curl http://localhost:8000/stats
```

### 停止服务

```bash
pkill -f uvicorn           # 停止 API
docker compose -f docker-compose-db.yml down   # 停止数据库（数据保留）
docker compose -f docker-compose-db.yml down -v # 停止数据库+删除数据
```

### 查看日志

```bash
docker logs geo-postgres    # PostGIS 日志
docker logs qdrant          # Qdrant 日志
docker logs neo4j           # Neo4j 日志
cat /tmp/api.log            # API 日志
```

### 开放端口

如需从外网访问服务，请在云服务器安全组放行 **TCP 8000** 端口后访问。
