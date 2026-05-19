"""
@brief Node gọi Tavily Web Search cho các claim cần thêm bằng chứng.
@details Node này không gọi LLM. Nó chỉ gọi Tavily cho claim đang NEI hoặc
         được đánh dấu needs_web=True, rồi ghi kết quả vào web_evidence.
"""

from app.agent.state import AgentState, SubClaim


def _should_search_claim(claim: SubClaim) -> bool:
    """
    @brief Xác định claim nào cần gọi Tavily.
    @details Sau judge_internal, điều kiện chính là verdict=NEI. Trường needs_web
             được giữ để hỗ trợ routing từ extract hoặc các fallback khác.
    """
    return claim.get("verdict") == "NEI" or bool(claim.get("needs_web"))


async def _search_claim_web(
    claim: SubClaim,
    category: str | None,
    max_results: int,
    search_depth: str,
) -> list[dict]:
    """
    @brief Gọi Tavily cho một claim và trả về danh sách evidence web.
    """
    from app.agent.tools.searcher import web_search

    return await web_search(
        query=claim["claim"],
        max_results=max_results,
        search_depth=search_depth,
        topic="news",
        category=category if category != "unknown" else None,
        required_terms=claim.get("entities", []),
    )


async def search_web(
    state: AgentState,
    max_results: int = 3,
    search_depth: str = "basic",
) -> dict:
    """
    @brief LangGraph node gọi Tavily cho các claim cần web evidence.
    @param state AgentState sau judge_internal.
    @param max_results Số kết quả Tavily tối đa cho mỗi claim.
    @param search_depth "basic" để tiết kiệm quota, "advanced" khi cần sâu hơn.
    @return Dict cập nhật sub_claims với web_evidence và tăng tavily_calls.
    """
    sub_claims = state.get("sub_claims", [])
    if not sub_claims:
        raise ValueError("Không có sub_claims để search_web xử lý")

    category = state.get("category")
    updated_claims: list[SubClaim] = []
    tavily_calls = int(state.get("tavily_calls", 0))

    for claim in sub_claims:
        updated_claim = SubClaim(**claim)
        if _should_search_claim(updated_claim):
            updated_claim["web_evidence"] = await _search_claim_web(
                updated_claim,
                category=category,
                max_results=max_results,
                search_depth=search_depth,
            )
            tavily_calls += 1
        updated_claims.append(updated_claim)

    return {
        "sub_claims": updated_claims,
        "tavily_calls": tavily_calls,
    }
