from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class SubClaim(TypedDict):
    """
    @brief Class biểu diễn 1 Sub-claim (luận điểm phụ) của bài báo
    """
    claim: str
    verdict: str | None          # SUPPORTED / REFUTED / NEI
    confidence: float | None
    reasoning: str | None        # Giải thích ngắn
    evidence: list[dict] | None  # [{source, title, snippet}]

class AgentState(TypedDict):
    """
    @brief State chính của luồng chạy LangGraph
    @details Các thuộc tính dùng lưu trữ kết quả trung gian giữa các node.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str              # Input gốc (text hoặc URL)
    article_text: str | None     # Nội dung bài báo (nếu input = URL)
    summary: str | None          # Đoạn text tóm tắt

    sub_claims: list[SubClaim]   # Danh sách luận điểm
    current_idx: int             # Chỉ số claim đang xử lý

    web_evidence: list[dict]     # Kết quả web (Tavily)
    kb_evidence: list[dict]      # Kết quả DB (pgvector)

    final_verdict: str | None
    confidence: float | None
    explanation: str | None
    sources: list[dict]
