"""
@brief Node: Tóm tắt bài báo + Trích xuất Sub-claims
@details Gộp 2 bước summarize và extract thành 1 lần gọi LLM duy nhất.
         Sử dụng Qwen (qwen/qwen3-32b) thông qua Groq API.
         Đầu ra: cập nhật `summary` và `sub_claims` trong AgentState.
"""

import json
import os
import re

from langchain_core.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

from app.agent.state import AgentState, SubClaim
from app.agent.core.prompts import SUMMARIZE_AND_EXTRACT_PROMPT


def _get_llm() -> BaseChatModel:
    """
    @brief Khởi tạo LLM GPT-OSS 120B qua Groq
    @return ChatGroq instance đã cấu hình
    """
    return ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.2,
        max_tokens=2048,
    )


def _parse_json_response(text: str) -> dict:
    """
    @brief Parse JSON từ response của LLM
    @details Xử lý các trường hợp LLM trả về markdown code block hoặc text thừa
    @param text: raw response text từ LLM
    @return dict chứa summary và claims
    @raises ValueError: nếu không parse được JSON hợp lệ
    """
    # Qwen/DeepSeek trả về <think>...</think> trước câu trả lời thật → loại bỏ
    think_match = re.search(r"<think>[\s\S]*?(?:</think>|$)", text)
    if think_match:
        text = text[think_match.end():].strip()

    # Nếu nằm trong code block ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    # Tìm JSON object đầu tiên trong text
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Không thể parse JSON từ phản hồi LLM: {e}\nRaw: {text}")

    # Validate cấu trúc
    if "summary" not in data or "claims" not in data:
        raise ValueError(f"JSON thiếu key 'summary' hoặc 'claims': {data}")
    if not isinstance(data["claims"], list) or len(data["claims"]) == 0:
        raise ValueError(f"'claims' phải là danh sách không rỗng: {data}")

    return data


async def summarize_and_extract(state: AgentState) -> dict:
    """
    @brief Node chính: Tóm tắt + Trích xuất sub-claims từ bài báo
    @param state: AgentState hiện tại (cần có user_input hoặc article_text)
    @return dict cập nhật vào state: summary, sub_claims
    """
    # Lấy văn bản cần xử lý (ưu tiên article_text nếu đã parse URL)
    article = state.get("article_text") or state.get("user_input", "")
    if not article.strip():
        raise ValueError("Không có nội dung bài báo để xử lý (user_input và article_text đều trống)")

    # Build prompt
    prompt = SUMMARIZE_AND_EXTRACT_PROMPT.format(article_text=article)

    # Gọi LLM
    llm = _get_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw_text = response.content

    # Parse kết quả
    result = _parse_json_response(raw_text)

    # Chuyển claims thành list[SubClaim]
    sub_claims: list[SubClaim] = [
        SubClaim(
            claim=claim_text,
            verdict=None,
            confidence=None,
            reasoning=None,
            evidence=None,
        )
        for claim_text in result["claims"]
    ]

    return {
        "summary": result["summary"],
        "sub_claims": sub_claims,
        "current_idx": 0,  # Reset index cho các node phía sau
    }
