"""
@brief Node extract cho workflow tiết kiệm API call.
@details Gộp tóm tắt, trích xuất claim, category, entity và routing hint
         vào một lần gọi Groq để các node retrieve/judge phía sau dùng lại.
"""

import json
import os
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.agent.core.prompts import EXTRACT_PROMPT
from app.agent.state import AgentState, SubClaim


VALID_CATEGORIES = {"bong-da", "bong-ro", "bong-chay", "tennis", "unknown"}
VALID_PRIORITIES = {"high", "medium", "low"}

CATEGORY_KEYWORDS = {
    "bong-ro": [
        "nba", "lebron", "lakers", "okc", "oklahoma city thunder", "basketball", "bóng rổ",
        "celtics", "warriors", "bulls", "mavericks", "nuggets", "knicks",
        "giannis", "antetokounmpo", "bucks", "milwaukee bucks",
    ],
    "tennis": ["tennis", "atp", "wta", "medvedev", "alcaraz", "djokovic", "monte carlo"],
    "bong-chay": ["mlb", "baseball", "bóng chày"],
    "bong-da": ["football", "soccer", "bóng đá", "champions league", "premier league", "man utd"],
}

ENTITY_ALIASES = {
    "Antetokunmpo": "Antetokounmpo",
    "Lebron James": "LeBron James",
    "Griezmamn": "Griezmann",
    "Griezzman": "Griezmann",
    "Lewandoski": "Lewandowski",
    "Lewandowsky": "Lewandowski",
}


def _get_llm() -> BaseChatModel:
    """
    @brief Khởi tạo LLM cho bước extract.
    @details Ưu tiên GPT-OSS trên Groq vì node này cần trả JSON có cấu trúc ổn định.
    """
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=os.getenv("GROQ_EXTRACT_MODEL", "openai/gpt-oss-120b"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
        max_tokens=2048,
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    """
    @brief Parse JSON từ phản hồi LLM.
    @details Xử lý các response có <think>...</think>, markdown code block hoặc text thừa.
    """
    think_match = re.search(r"<think>[\s\S]*?(?:</think>|$)", text)
    if think_match:
        text = text[think_match.end():].strip()

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Không thể parse JSON từ phản hồi LLM: {exc}\nRaw: {text}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Extract response phải là JSON object: {data}")
    if not data.get("summary"):
        raise ValueError(f"Extract response thiếu summary: {data}")
    if not isinstance(data.get("claims"), list) or not data["claims"]:
        raise ValueError(f"Extract response thiếu claims hợp lệ: {data}")

    return data


def _as_string_list(value: Any) -> list[str]:
    """
    @brief Chuẩn hóa một giá trị bất kỳ thành list[str] không rỗng.
    """
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_known_entities(text: str) -> str:
    """
    @brief Sửa một số typo/casing entity thể thao phổ biến trước khi các node sau xử lý.
    """
    normalized = str(text or "")
    for wrong, correct in ENTITY_ALIASES.items():
        normalized = re.sub(re.escape(wrong), correct, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<!Antoine )\bGriezmann\b", "Antoine Griezmann", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<!Robert )\bLewandowski\b", "Robert Lewandowski", normalized, flags=re.IGNORECASE)
    return normalized


def _normalize_claim(raw_claim: Any) -> SubClaim | None:
    """
    @brief Chuẩn hóa một claim từ JSON của LLM sang SubClaim dùng trong AgentState.
    """
    if isinstance(raw_claim, str):
        claim_text = _normalize_known_entities(raw_claim.strip())
        entities: list[str] = []
        time_refs: list[str] = []
        needs_web = False
        priority = "medium"
    elif isinstance(raw_claim, dict):
        claim_text = _normalize_known_entities(str(raw_claim.get("claim", "")).strip())
        entities = [_normalize_known_entities(entity) for entity in _as_string_list(raw_claim.get("entities"))]
        time_refs = _as_string_list(raw_claim.get("time_refs"))
        needs_web = bool(raw_claim.get("needs_web", False))
        priority = str(raw_claim.get("priority", "medium")).strip().lower()
    else:
        return None

    if not claim_text:
        return None
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    return SubClaim(
        claim=claim_text,
        entities=entities,
        time_refs=time_refs,
        needs_web=needs_web,
        priority=priority,
        kb_evidence=None,
        web_evidence=None,
        verdict=None,
        confidence=None,
        reasoning=None,
        evidence=None,
    )


def _infer_category_from_text(text: str) -> str | None:
    """
    @brief Suy luận category bằng keyword rõ ràng để sửa lỗi phân loại của LLM.
    """
    lowered = text.lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in lowered)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else None


async def extract(state: AgentState) -> dict:
    """
    @brief Node chính để tóm tắt và trích xuất dữ liệu kiểm chứng từ input text.
    @param state AgentState hiện tại, cần có user_input hoặc article_text.
    @return Dict cập nhật state: summary, category, global_entities, sub_claims, current_idx, llm_calls.
    """
    article = state.get("article_text") or state.get("user_input", "")
    if not article.strip():
        raise ValueError("Không có nội dung để extract (user_input và article_text đều trống)")

    prompt = EXTRACT_PROMPT.format(article_text=article)
    response = await _get_llm().ainvoke([HumanMessage(content=prompt)])
    result = _parse_json_response(response.content)

    category = str(result.get("category", "unknown")).strip()
    if category not in VALID_CATEGORIES:
        category = "unknown"

    sub_claims = [
        claim
        for claim in (_normalize_claim(raw_claim) for raw_claim in result["claims"])
        if claim is not None
    ]
    if not sub_claims:
        raise ValueError(f"Không extract được claim hợp lệ từ response: {result}")

    category_text = " ".join([
        article,
        str(result.get("summary", "")),
        " ".join(_as_string_list(result.get("global_entities"))),
        " ".join(entity for claim in sub_claims for entity in claim.get("entities", [])),
    ])
    inferred_category = _infer_category_from_text(category_text)
    if inferred_category:
        category = inferred_category

    return {
        "summary": str(result["summary"]).strip(),
        "category": category,
        "global_entities": _as_string_list(result.get("global_entities")),
        "sub_claims": sub_claims,
        "current_idx": 0,
        "llm_calls": int(state.get("llm_calls", 0)) + 1,
    }
