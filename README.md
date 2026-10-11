# 🗺️ 地质数据智能检索 Demo

> PostGIS 空间检索 + Qdrant 向量语义检索 + Neo4j 知识图谱 + LangGraph AI 地质助手  
> 面向 AI 探矿智能体的多模态数据基础设施

## 🎯 项目简介

本项目是一个面向地质勘探领域的智能数据检索平台，整合空间数据库、向量数据库、知识图谱和 LangGraph Agent，实现对地质数据的多维度、多模态智能检索。

| 模块 | 技术 | 用途 |
|------|------|------|
| 空间数据库 | **PostGIS** | 钻孔、化探、矿区等空间数据的存储与范围查询 |
| 向量数据库 | **Qdrant** | 基于真实 Embedding 的语义检索，超越关键词匹配 |
| 知识图谱 | **Neo4j** | 矿物-矿床-蚀变-岩性的关联关系查询与可视化 |
| AI 地质助手 | **LangChain / LangGraph** | 根据自然语言问题自主选择工具，综合多个数据源生成回答 |

前端首页已经内置 **AI 地质助手（LangGraph Agent）** 面板。用户可以直接输入自然语言问题，例如：

- “系统里有哪些跟锂矿提取工艺相关的文档？”
- “宜春钽铌矿有哪些钻孔？并总结锂钽铌品位情况”
- “帮我比较宜春锂矿相关矿区、钻孔和知识图谱关系”

AI 助手会根据问题自动调用后端工具，而不是让用户手动决定查 PostGIS、Qdrant 还是 Neo4j。

## 🏗️ 技术架构

```text
┌──────────────────────────────────────────────────────────────┐
│                         浏览器首页                            │
│  地图 / 钻孔 / 语义检索 / 空间检索 / 知识图谱 / AI 地质助手     │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                       FastAPI 后端                            │
│               app/main.py + agent_routes.py                  │
├──────────────┬───────────────┬───────────────┬───────────────┤
│   PostGIS    │    Qdrant     │     Neo4j     │  LangGraph    │
│  空间检索     │  语义检索      │   图谱查询     │ ReAct Agent   │
│ ST_DWithin   │ COSINE 相似度  │ Cypher 查询   │ Tool Calling  │
└──────────────┴───────────────┴───────────────┴───────┬───────┘
                                                        │
                                                        ▼
                                 火山方舟 OpenAI 兼容接口 / deepseek-v3-2
```

LangGraph Agent 使用 “ReAct 节点 + Tools 节点” 架构：

1. 用户在页面 AI 助手输入自然语言问题。
2. FastAPI 的 `POST /agent/chat` 接收问题。
3. LangGraph 中的 LLM 节点判断需要哪些工具。
4. Tools 节点执行数据库查询工具。
5. LLM 汇总 PostGIS、Qdrant、Neo4j 等结果并返回中文回答。

## 🔧 技术栈详解

### 1. PostGIS — 空间检索

- **用途**：存储钻孔位置、化探采样点、矿区边界等 GIS 数据
- **核心功能**：`ST_DWithin` 范围查询，按经纬度和半径检索附近钻孔
- **数据量**：18 个钻孔、13 个化探样品、11 个矿区

### 2. Qdrant — 语义检索

- **用途**：基于向量相似度的文档语义检索
- **Embedding 模型**：`BAAI/bge-small-zh-v1.5`（通过 fastembed/ONNX 推理，无需 PyTorch）
- **向量维度**：512 维，COSINE 距离
- **模型缓存**：`/tmp/fastembed_cache` 通过 Docker named volume `fastembed_cache` 持久化
- **核心优势**：真实语义匹配，而非关键词匹配
  - 查询“怎么从锂云母提锂” → 匹配到“锂云母提取碳酸锂工艺研究”
  - 查询“世界最大钨矿” → 匹配到“浮梁朱溪超大型钨矿”
  - 查询“稀土矿是什么类型” → 匹配到“龙南离子吸附型重稀土矿”
- **数据量**：13 篇地质文档（含宜春锂矿、德兴铜矿、赣南钨矿等）

### 3. Neo4j — 知识图谱

- **用途**：矿物-矿床-蚀变-岩性之间的关联关系查询
- **实体类型**：MineArea（矿区）、Mineral（矿物）、Alteration（蚀变）、RockType（岩性）、Region（区域）、Process（工艺）
- **关系类型**：含有、蚀变类型、赋存于、位于、提锂工艺、正相关
- **数据量**：28 个实体、25 条关系
- **可视化**：vis.js 交互式力导向图，支持拖拽和缩放

### 4. LangGraph AI 地质助手

- **框架**：LangChain Core + LangChain OpenAI + LangGraph
- **模型**：火山方舟 OpenAI 兼容接口，默认 `deepseek-v3-2`
- **后端入口**：`app/agent_routes.py`
- **图编排**：`app/agent_geo_graph.py`
- **工具集合**：`app/agent_geo_tools.py`
- **前端入口**：首页 `AI 地质助手（LangGraph Agent）` 面板

Agent 当前包含 6 个工具：

| 工具 | 数据源 | 能力 |
|------|--------|------|
| `list_mining_areas` | PostGIS | 查询矿区列表 |
| `list_drillholes_by_mine` | PostGIS | 按矿区查询钻孔 |
| `search_drillholes_nearby` | PostGIS | 按经纬度和半径查询附近钻孔 |
| `query_geochemistry` | PostGIS | 查询化探样品 |
| `semantic_search_documents` | Qdrant | 查询语义相关地质文档 |
| `query_knowledge_graph` | Neo4j | 查询知识图谱实体关系 |

### 5. FastAPI 后端

- **框架**：FastAPI + Uvicorn
- **页面端点**：
  - `GET /` — 前端首页
  - `GET /docs` — Swagger API 文档
- **数据 API**：
  - `GET /stats` — 数据统计
  - `GET /drillholes` — 钻孔数据列表
  - `GET /drillholes/nearby` — 空间范围查询（经纬度 + 半径）
  - `GET /mining-areas` — 矿区数据列表
  - `GET /geochemistry` — 化探样品列表
  - `GET /documents` — 文档列表
  - `POST /search/semantic` — Qdrant 语义检索
  - `GET /knowledge-graph/sample` — 示例知识图谱
  - `GET /knowledge-graph/query` — 知识图谱查询
- **Agent API**：
  - `POST /agent/chat` — AI 助手一次性问答
  - `POST /agent/chat/trace` — 返回中间工具调用过程，适合调试和演示
  - `GET /agent/health` — Agent 健康检查

## 🤖 AI 助手使用方式

### 浏览器使用

打开首页：

```text
http://服务器IP:8000/
```

页面顶部统计卡片下方有 **AI 地质助手（LangGraph Agent）** 面板。输入问题后点击“询问 AI 助手”，页面会展示：

- Agent 最终中文回答
- 工具调用次数 `tool_calls_count`
- 消息轮次 `messages_count`

### API 使用

```bash
curl -X POST http://服务器IP:8000/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"系统里有哪些跟锂矿提取工艺相关的文档？"}'
```

带 trace 的调试请求：

```bash
curl -X POST http://服务器IP:8000/agent/chat/trace \
  -H 'Content-Type: application/json' \
  -d '{"question":"宜春钽铌矿有哪些钻孔？另外用知识图谱看一下宜春周边有什么实体"}'
```

健康检查：

```bash
curl http://服务器IP:8000/agent/health
```

## 📦 数据覆盖

### 宜春地区（锂矿/钽铌矿）

- 宜春钽铌矿、花桥锂矿、九岭锂矿
- 钻孔 ZK001-ZK007，化探样品 GH001-GH009

### 江西各地矿床（扩展数据）

| 矿区 | 类型 | 状态 | 亮点 |
|------|------|------|------|
| 德兴铜矿 | 斑岩铜矿 | 生产中 | 铜金属储量 900 万吨 |
| 大余西华山钨矿 | 石英脉型黑钨矿 | 资源枯竭 | 世界钨都（1907 年发现） |
| 贵溪冷水坑银矿 | 斑岩型银矿 | 生产中 | 亚洲最大银矿，银 9400 吨 |
| 龙南稀土矿 | 离子吸附型重稀土 | 保护性开发 | 世界最大重稀土矿床 |
| 浮梁朱溪钨矿 | 矽卡岩型白钨矿 | 勘查中 | 世界最大钨矿，WO₃ 344 万吨 |
| 德兴金山金矿 | 造山型金矿 | 生产中 | 江南最大金矿，金 202.5 吨 |
| 武宁大湖塘钨矿 | 细脉浸染型白钨矿 | 生产中 | 赣北钨矿支柱 |

## 🚀 部署方式

当前推荐使用根目录 `docker-compose.yml` 启动完整服务：

```bash
# 1. 准备环境变量（首次部署）：把模板复制成 .env 并填入真实 API Key
cp .env.example .env
#    编辑 .env，设置 AGENT_LLM_API_KEY=<你的火山方舟 API Key>
#    .env 已被 .gitignore 忽略，不会提交到仓库

# 2. 启动全部服务
docker compose up -d --build
```

> ⚠️ **密钥安全**：`AGENT_LLM_API_KEY` 等敏感信息只放在本地 `.env` 中，
> `docker-compose.yml` 仅通过 `${VAR}` 引用，仓库里不保存任何真实密钥。

重启 API 服务：

```bash
docker compose up -d --force-recreate geo-api
```

查看服务状态：

```bash
docker compose ps
```

### Docker 容器

| 服务 | 镜像/构建 | 端口 | 说明 |
|------|-----------|------|------|
| PostGIS | `postgis/postgis:16-3.4` | 5432 | 空间数据库 |
| Qdrant | `qdrant/qdrant:latest` | 6333/6334 | 向量数据库 |
| Neo4j | `neo4j:5-community` | 7474/7687 | 知识图谱 |
| geo-api | `./app` | 8000 | FastAPI + 前端 + Agent |

### 关键环境变量

| 环境变量 | 示例值 | 说明 |
|----------|--------|------|
| `DB_HOST` | `geo-postgres` | PostGIS 容器主机名 |
| `QDRANT_HOST` | `qdrant` | Qdrant 容器主机名 |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt 地址 |
| `NEO4J_PASSWORD` | `geo12345` | Neo4j 密码 |
| `AGENT_LLM_BASE_URL` | `https://ark.cn-beijing.volces.com/api/coding/v3` | 火山方舟 OpenAI 兼容入口 |
| `AGENT_LLM_MODEL` | `deepseek-v3-2` | Agent 使用的模型名 |
| `AGENT_LLM_API_KEY` | 从本地 `.env` 读取，切勿提交仓库 | 火山方舟 API Key |
| `FASTEMBED_CACHE_DIR` | `/tmp/fastembed_cache` | fastembed 模型缓存目录 |
| `FASTEMBED_LOCAL_FILES_ONLY` | `true` | 优先使用本地缓存，避免容器重建后等待 HuggingFace 超时 |

## 📁 项目结构

```text
geo-demo/
├── docker-compose.yml          # 完整服务编排：PostGIS / Qdrant / Neo4j / geo-api
├── docker-compose-db.yml       # 仅数据库服务编排
├── init_sql/
│   ├── 01_init_geology.sql     # 宜春地区初始数据
│   └── 02_jiangxi_mines.sql    # 江西各地矿床扩展数据
├── app/
│   ├── main.py                 # FastAPI 后端入口，挂载静态页面和 Agent router
│   ├── agent_geo_tools.py      # LangChain tools：PostGIS / Qdrant / Neo4j 查询工具
│   ├── agent_geo_graph.py      # LangGraph StateGraph：ReAct Agent 编排
│   ├── agent_routes.py         # /agent/chat、/agent/chat/trace、/agent/health
│   ├── init_qdrant_vectors.py  # Qdrant 向量数据初始化
│   ├── init_neo4j.py           # Neo4j 知识图谱初始化
│   ├── requirements.txt        # Python 依赖
│   └── static/
│       ├── index.html          # 前端页面，包含 AI 地质助手面板
│       ├── leaflet.css         # 地图样式（本地）
│       ├── leaflet.js          # 地图库（本地）
│       ├── vis-network.min.js  # 知识图谱可视化（本地）
│       └── images/             # 地图图标
└── README.md
```

## 💡 设计亮点

1. **全能中心 Agent**：一个 LangGraph ReAct Agent 统一调度 6 个数据库工具，避免用户手动组合多个 API。
2. **真实语义检索**：使用 BAAI/bge-small-zh-v1.5 中文向量模型（fastembed/ONNX 推理），无需 GPU。
3. **模型缓存持久化**：`fastembed_cache` Docker volume 保留 ONNX 模型，容器重建后首次语义检索仍可快速响应。
4. **全本地化前端资源**：Leaflet、vis-network 等资源均为本地文件，无 CDN 依赖。
5. **地图瓦片适配国内网络**：使用高德地图瓦片服务。
6. **轻量部署**：整个系统可运行在 4GB 内存云服务器上。

## 🔑 默认开发配置

| 配置项 | 值 |
|--------|-----|
| PostGIS 用户/密码 | `geo` / `geo123` |
| PostGIS 数据库 | `geology` |
| Neo4j 用户/密码 | `neo4j` / `geo12345` |
| Qdrant 端口 | 6333 (REST) / 6334 (gRPC) |
| Embedding 模型 | `BAAI/bge-small-zh-v1.5` |
| 向量维度 | 512 |
| Agent LLM | `deepseek-v3-2` |
| Agent API 前缀 | `/agent` |

## 📄 License

本项目为演示 Demo，仅供学习参考。
