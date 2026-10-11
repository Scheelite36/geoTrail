"""agent_geo_graph.py: LangGraph StateGraph for the geo-demo Agent.

【这个文件画了什么图】

    用户问句
       │
       ▼
    ┌──────────────┐  没新工具调用      ┌─────┐
    │ agent (LLM)  │ ─────────────────▶│ END │
    └──────┬───────┘                   └─────┘
           │ 有 ToolCall
           ▼
    ┌──────────────┐
    │ tools 节点   │ ── 真去执行工具 ──▶ 把 ToolMessage
    │ (ToolNode)   │                     塞回 state
    └──────┬───────┘
           │
           └────── 回到 agent 节点

【核心抽象的 Java 类比】

    StateGraph                    ≈ Spring State Machine 的 builder
    State (TypedDict)             ≈ 共享的 ProcessVariables（每个节点读写）
    add_messages reducer          ≈ List append（不是覆盖），ADK 框架自动合并
    ToolNode                      ≈ 自动调用所有 ToolCall 的内置节点
    add_conditional_edges         ≈ 条件状态转移
    compile()                     ≈ build() 返回可运行实例

【ReAct 关键 invariant】

    LLM 收到的上下文永远包含完整的 messages 历史：
        [SystemMessage, HumanMessage, AIMessage(tool_calls=[...]),
         ToolMessage(tool结果), AIMessage(tool_calls=[...]),
         ToolMessage(tool结果), AIMessage(最终回答)]
    这意味着 LLM 每次决策时都能看到之前调过哪些工具、结果是啥。
    所以 LangGraph 的 state 设计成 messages 列表 + add_messages reducer。
"""

from __future__ import annotations
import logging
import os
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agent_geo_tools import ALL_TOOLS

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是江西省地质勘探数据问答助手，叫"地质小助"。

你能访问 6 类工具：
1. list_mining_areas: 列出所有矿区概览（先调这个全局了解）
2. list_drillholes_by_mine: 按矿区名查钻孔
3. search_drillholes_nearby: 按经纬度+半径查附近钻孔
4. query_geochemistry: 化探采样元素含量
5. semantic_search_documents: 地质文献语义检索（自然语言问概念时用）
6. query_knowledge_graph: 矿物-矿床-蚀变-工艺关联图谱

工作纪律：
- 回答前**必须**先调用工具拿到真实数据，不要凭空编造
- 用户问综合问题（如"某矿现状+提取工艺"），分多步调用：先空间数据，再图谱，再文献
- 工具返回 JSON 后，用中文段落总结给用户，不要直接 dump JSON
- 如果工具报错（error 字段），告诉用户具体哪一步失败了
- 涉及具体矿区时优先用矿区名（list_drillholes_by_mine），别先猜坐标
- 一次最多调 6 次工具，避免死循环
- 最后用结构化 markdown 回答（## 数据 / ## 分析 / ## 引用 三段式）"""


class AgentState(TypedDict):
    """状态机的 state schema。

    messages 字段使用 Annotated[..., add_messages] 是 LangGraph 的关键约定：
    - 普通 TypedDict 字段被节点返回时是**覆盖**语义
    - 加 add_messages reducer 后变成**追加**语义
    - 这样多个节点都能往 messages 里加新消息而不丢失历史
    """

    messages: Annotated[Sequence[AnyMessage], add_messages]


def _build_llm() -> ChatOpenAI:
    """构造接 LLM 的客户端。

    通过 OpenAI 兼容协议连火山方舟（base_url 指过去就行）。
    bind_tools 在外层调用，把 6 个工具的 schema 注入到 LLM 上下文。
    """
    return ChatOpenAI(
        model=os.getenv("AGENT_LLM_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("AGENT_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        base_url=os.getenv(
            "AGENT_LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3"
        ),
        temperature=0.0,
        timeout=60,
    )


_GRAPH_SINGLETON = None


def get_agent_graph():
    """获取已编译的 LangGraph（单例）。

    首次调用时构造图：定义节点 → 定义边 → compile()。
    后续直接返回缓存实例，避免重复构造。
    """
    global _GRAPH_SINGLETON
    if _GRAPH_SINGLETON is not None:
        return _GRAPH_SINGLETON

    llm = _build_llm().bind_tools(ALL_TOOLS)
    tool_node = ToolNode(ALL_TOOLS)

    def agent_node(state: AgentState) -> dict:
        """LLM 节点：把 messages 喂给 LLM，拿回 AIMessage（可能含 tool_calls）。"""
        messages = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """条件边：看 LLM 最新消息有没有 tool_calls，有就转 tools，没有就结束。"""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", END: END}
    )
    workflow.add_edge("tools", "agent")

    _GRAPH_SINGLETON = workflow.compile()
    logger.info("LangGraph agent compiled with %d tools", len(ALL_TOOLS))
    return _GRAPH_SINGLETON

if __name__ == "__main__":
    graph = get_agent_graph()
    print(graph)