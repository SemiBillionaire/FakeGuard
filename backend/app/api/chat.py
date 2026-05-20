import json
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

router = APIRouter()


class ChatRequest(BaseModel):
    """
    @brief Model đầu vào cho endpoint fact-check.
    """
    text: str = Field(..., min_length=1, description="Đoạn tin hoặc claim cần kiểm chứng")


class ClaimResponse(BaseModel):
    """
    @brief Một sub-claim đã được fact-check.
    """
    claim: str
    verdict: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    entities: list[str] = Field(default_factory=list)
    time_refs: list[str] = Field(default_factory=list)


class SourceResponse(BaseModel):
    """
    @brief Nguồn bằng chứng liên quan cho verdict cuối.
    """
    title: str
    url: str
    relevance: str | None = None
    claim: str | None = None
    verdict: str | None = None


class ChatResponse(BaseModel):
    """
    @brief Response chuẩn hóa trả về cho frontend/client.
    """
    verdict: str | None = None
    confidence: float | None = None
    summary: str | None = None
    explanation: str | None = None
    category: str | None = None
    claims: list[ClaimResponse] = Field(default_factory=list)
    sources: list[SourceResponse] = Field(default_factory=list)
    llm_calls: int = 0
    tavily_calls: int = 0


def _build_initial_state(text: str) -> dict[str, Any]:
    """
    @brief Tạo AgentState ban đầu để gọi LangGraph.
    """
    return {
        "messages": [],
        "user_input": text,
        "article_text": None,
        "summary": None,
        "category": None,
        "global_entities": [],
        "sub_claims": [],
        "current_idx": 0,
        "web_evidence": [],
        "kb_evidence": [],
        "final_verdict": None,
        "confidence": None,
        "explanation": None,
        "sources": [],
        "llm_calls": 0,
        "tavily_calls": 0,
    }


def _format_claims(sub_claims: list[dict]) -> list[ClaimResponse]:
    """
    @brief Chuyển sub_claims thô từ state sang payload gọn cho API.
    """
    claims: list[ClaimResponse] = []
    for claim in sub_claims or []:
        claims.append(
            ClaimResponse(
                claim=str(claim.get("claim", "")),
                verdict=claim.get("verdict"),
                confidence=claim.get("confidence"),
                reasoning=claim.get("reasoning"),
                entities=list(claim.get("entities", []) or []),
                time_refs=list(claim.get("time_refs", []) or []),
            )
        )
    return claims


def _format_sources(sources: list[dict]) -> list[SourceResponse]:
    """
    @brief Chuẩn hóa danh sách source để trả về client.
    """
    payload: list[SourceResponse] = []
    for source in sources or []:
        payload.append(
            SourceResponse(
                title=str(source.get("title", "")),
                url=str(source.get("url", "")),
                relevance=source.get("relevance"),
                claim=source.get("claim"),
                verdict=source.get("verdict"),
            )
        )
    return payload


def _to_response(result: dict[str, Any]) -> ChatResponse:
    """
    @brief Map AgentState sau khi chạy graph sang response API.
    """
    return ChatResponse(
        verdict=result.get("final_verdict"),
        confidence=result.get("confidence"),
        summary=result.get("summary"),
        explanation=result.get("explanation"),
        category=result.get("category"),
        claims=_format_claims(result.get("sub_claims", [])),
        sources=_format_sources(result.get("sources", [])),
        llm_calls=int(result.get("llm_calls", 0) or 0),
        tavily_calls=int(result.get("tavily_calls", 0) or 0),
    )


def _format_runtime_error(exc: Exception) -> tuple[int, str]:
    """
    @brief Chuyển lỗi runtime thành HTTP status và message gọn.
    """
    message = str(exc).replace("\n", " ").strip()
    lowered = message.lower()

    if "rate limit" in lowered or "rate_limit" in lowered:
        return 429, "LLM API đang bị rate limit. Hãy thử lại sau."
    if "tavily" in lowered and ("api" in lowered or "search" in lowered):
        return 502, "Lỗi khi truy vấn Tavily."
    if "database" in lowered or "postgres" in lowered or "sqlalchemy" in lowered:
        return 502, "Lỗi khi truy vấn cơ sở dữ liệu nội bộ."

    return 500, f"Không thể xử lý yêu cầu fact-check: {message[:200]}"


async def _run_agent(text: str) -> ChatResponse:
    """
    @brief Gọi LangGraph agent và trả về response chuẩn hóa.
    """
    from app.agent.graph import agent

    result = await agent.ainvoke(_build_initial_state(text))
    return _to_response(result)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    @brief Endpoint JSON thường để fact-check một đoạn văn bản.
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Trường 'text' không được để trống.")

    try:
        return await _run_agent(text)
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    @brief Endpoint SSE đơn giản, hiện stream một kết quả hoàn chỉnh khi graph xong.
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Trường 'text' không được để trống.")

    async def event_generator():
        try:
            response = await _run_agent(text)
            payload = json.dumps(response.model_dump(), ensure_ascii=False)
            yield f"event: result\ndata: {payload}\n\n"
        except Exception as exc:
            _, detail = _format_runtime_error(exc)
            payload = json.dumps({"error": detail}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
