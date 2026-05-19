"""
@brief Khai báo LangGraph workflow cho agent kiểm chứng tin thể thao.
@details Luồng chính: extract -> retrieve_internal -> judge_internal,
         nếu còn claim NEI hoặc cần web thì search_web -> judge_after_web,
         cuối cùng synthesize kết quả.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    extract,
    judge_after_web,
    judge_internal,
    retrieve_internal,
    search_web,
    synthesize,
)
from app.agent.state import AgentState


NodeFn = Callable[[AgentState], Awaitable[dict[str, Any]]]


def _claim_needs_web(claim: dict[str, Any]) -> bool:
    """
    @brief Kiểm tra một sub-claim có cần đi qua Tavily hay không.
    @details Claim cần web khi judge_internal trả verdict NEI hoặc bật cờ needs_web=True.
    """
    verdict = str(claim.get("verdict") or "").strip().upper()
    return verdict == "NEI" or bool(claim.get("needs_web"))


def route_after_internal_judge(state: AgentState) -> str:
    """
    @brief Router sau node judge_internal.
    @return "search_web" nếu còn claim cần tìm web, ngược lại "synthesize".
    """
    sub_claims = state.get("sub_claims", [])
    if any(_claim_needs_web(claim) for claim in sub_claims):
        return "search_web"
    return "synthesize"


def build_graph(
    node_overrides: dict[str, NodeFn] | None = None,
    interrupt_after: list[str] | None = None,
):
    """
    @brief Tạo và compile LangGraph cho pipeline kiểm chứng.
    @param node_overrides Cho phép test thay node thật bằng fake node để không gọi API/DB.
    @param interrupt_after Dừng graph sau node chỉ định để test prototype theo từng bước.
    @return Compiled LangGraph có thể invoke/ainvoke từ API hoặc script test.
    """
    nodes: dict[str, NodeFn] = {
        "extract": extract,
        "retrieve_internal": retrieve_internal,
        "judge_internal": judge_internal,
        "search_web": search_web,
        "judge_after_web": judge_after_web,
        "synthesize": synthesize,
    }
    if node_overrides:
        nodes.update(node_overrides)

    graph = StateGraph(AgentState)

    graph.add_node("extract", nodes["extract"])
    graph.add_node("retrieve_internal", nodes["retrieve_internal"])
    graph.add_node("judge_internal", nodes["judge_internal"])
    graph.add_node("search_web", nodes["search_web"])
    graph.add_node("judge_after_web", nodes["judge_after_web"])
    graph.add_node("synthesize", nodes["synthesize"])

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "retrieve_internal")
    graph.add_edge("retrieve_internal", "judge_internal")
    graph.add_conditional_edges(
        "judge_internal",
        route_after_internal_judge,
        {
            "search_web": "search_web",
            "synthesize": "synthesize",
        },
    )
    graph.add_edge("search_web", "judge_after_web")
    graph.add_edge("judge_after_web", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile(interrupt_after=interrupt_after)


agent = build_graph()
