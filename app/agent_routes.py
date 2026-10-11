"""agent_routes.py: FastAPI router exposing the LangGraph agent over HTTP.

提供两个端点：
    POST /agent/chat       —— 一次性返回完整答案
    POST /agent/chat/trace —— 返回包含中间工具调用过程的 trace（调试/演示用）

这两个端点共享同一个编译后的 LangGraph 实例（agent_geo_graph.get_agent_graph）。
"""

from __future__ import annotations
import logging
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agent_geo_graph import get_agent_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    """对话请求体。

    history 字段可选：传入 [{role, content}, ...] 列表实现多轮对话。
    role 取值: "user" | "assistant"
    """

    question: str
    history: Optional[List[dict]] = None


def _to_lc_messages(history: Optional[List[dict]], question: str) -> list:
    """把前端传的简单 history dict 列表转成 LangChain Message 对象。"""
    msgs: list = []
    if history:
        for h in history:
            role = (h.get("role") or "").lower()
            content = h.get("content") or ""
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=question))
    return msgs


@router.post("/chat")
def chat(req: ChatRequest) -> dict:
    """一次性问答端点：返回 LLM 最终回答。

    内部流程：
        1. 把用户输入转成 LangChain Message
        2. graph.invoke 同步跑完整个 ReAct 循环
        3. 取出最后一条 AIMessage 作为答案
    """
    try:
        graph = get_agent_graph()
        messages = _to_lc_messages(req.history, req.question)
        result = graph.invoke({"messages": messages}, config={"recursion_limit": 20})
        final = result["messages"][-1]
        tool_calls_count = sum(
            1
            for m in result["messages"]
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )
        return {
            "question": req.question,
            "answer": getattr(final, "content", str(final)),
            "tool_calls_count": tool_calls_count,
            "messages_count": len(result["messages"]),
        }
    except Exception as e:
        logger.exception("agent chat failed")
        return {"question": req.question, "error": str(e)}


@router.post("/chat/trace")
def chat_trace(req: ChatRequest) -> dict:
    """带 trace 的问答：返回完整的 messages 链路（调试/演示用）。

    返回的 trace 数组每项包含：
        type: 消息类型（system/human/ai/tool）
        content: 文本内容
        tool_calls: AI 决定调的工具列表（仅 ai 类型）
        tool_name: 该 ToolMessage 来自哪个工具（仅 tool 类型）
    前端可直接渲染成时间轴，让用户看到 Agent 的"思考过程"。
    """
    try:
        graph = get_agent_graph()
        messages = _to_lc_messages(req.history, req.question)
        result = graph.invoke({"messages": messages}, config={"recursion_limit": 20})

        trace: List[dict] = []
        for m in result["messages"]:
            entry: dict[str, Any] = {"content": getattr(m, "content", "")}
            if isinstance(m, SystemMessage):
                entry["type"] = "system"
            elif isinstance(m, HumanMessage):
                entry["type"] = "human"
            elif isinstance(m, AIMessage):
                entry["type"] = "ai"
                tc = getattr(m, "tool_calls", None) or []
                entry["tool_calls"] = [
                    {"name": t.get("name"), "args": t.get("args")} for t in tc
                ]
            elif isinstance(m, ToolMessage):
                entry["type"] = "tool"
                entry["tool_name"] = getattr(m, "name", "")
            else:
                entry["type"] = type(m).__name__
            trace.append(entry)

        final = result["messages"][-1]
        return {
            "question": req.question,
            "answer": getattr(final, "content", str(final)),
            "trace": trace,
        }
    except Exception as e:
        logger.exception("agent chat/trace failed")
        return {"question": req.question, "error": str(e)}


@router.get("/health")
def agent_health() -> dict:
    """Agent 子系统健康检查：试图编译图、返回工具列表。"""
    try:
        graph = get_agent_graph()
        from agent_geo_tools import ALL_TOOLS

        return {
            "status": "ok",
            "tools": [t.name for t in ALL_TOOLS],
            "graph_nodes": list(graph.nodes.keys()),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
