"""
@brief Định nghĩa các Edge và Node cho LangGraph
@details Đây là Entry Point của luồng AI kiểm chứng tin giả
Tạo stategraph với thứ tự: summarize_and_extract -> ... -> retriever <-> verifier -> synthesizer
"""

from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes import summarize_and_extract

# Các node wrapper function sẽ được cài đặt và import ở đây


def build_graph():
    """
    @brief Tạo cấu trúc Langgraph
    @return Compiled Graph
    """
    g = StateGraph(AgentState)

    # ── Node 1: Tóm tắt + Trích xuất Sub-claims ──
    g.add_node("summarize_and_extract", summarize_and_extract)

    # ── Edges ──
    g.add_edge(START, "summarize_and_extract")
    g.add_edge("summarize_and_extract", END)  # TODO: nối tiếp sang node tiếp theo

    # Define thêm Nodes & Edges ở đây khi triển khai các bước tiếp theo

    return g.compile()


agent = build_graph()
