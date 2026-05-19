from typing import Annotated
from typing_extensions import NotRequired, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class SubClaim(TypedDict):
    """
    @brief Class biểu diễn 1 sub-claim trong pipeline kiểm chứng.
    @details Mỗi claim tự giữ entity, bằng chứng và kết quả judge để các node sau
             không phải dùng danh sách evidence cấp state gây lệch index.
    """
    claim: str
    entities: NotRequired[list[str]]
    time_refs: NotRequired[list[str]]
    needs_web: NotRequired[bool]
    priority: NotRequired[str]       # high / medium / low

    kb_evidence: NotRequired[list[dict] | None]
    web_evidence: NotRequired[list[dict] | None]

    verdict: NotRequired[str | None]       # SUPPORTED / REFUTED / NEI
    confidence: NotRequired[float | None]
    reasoning: NotRequired[str | None]
    evidence: NotRequired[list[dict] | None]

class AgentState(TypedDict):
    """
    @brief State chính của luồng chạy LangGraph
    @details Các thuộc tính dùng lưu trữ kết quả trung gian giữa các node.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str              # Input gốc (text hoặc URL)
    article_text: str | None     # Nội dung bài báo (nếu input = URL)
    summary: str | None          # Đoạn text tóm tắt
    category: str | None         # Môn thể thao: bong-da / bong-ro / tennis / bong-chay / unknown
    global_entities: list[str]   # Entity chung toàn bài

    sub_claims: list[SubClaim]   # Danh sách luận điểm
    current_idx: int             # Chỉ số claim đang xử lý

    web_evidence: list[dict]     # Kết quả web (Tavily)
    kb_evidence: list[dict]      # Kết quả DB (pgvector)

    final_verdict: str | None
    confidence: float | None
    explanation: str | None
    sources: list[dict]

    llm_calls: int               # Số lần gọi LLM trong workflow chính
    tavily_calls: int            # Số lần gọi Tavily API
