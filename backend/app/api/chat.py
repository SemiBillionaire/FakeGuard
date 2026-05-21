import json
import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import AsyncSessionLocal
from app.services.chat_history import (
    build_last_message_preview,
    build_session_title,
    create_chat_message,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_messages,
    list_chat_sessions,
    normalize_sport_category,
    update_chat_session_metadata,
)


load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

router = APIRouter()

DEFAULT_SESSION_TITLE = "Cuộc trò chuyện mới"


class ChatRequest(BaseModel):
    """
    @brief Model đầu vào cho endpoint fact-check.
    """

    session_id: str | None = Field(default=None, description="Session hiện tại; null nếu tạo chat mới")
    text: str = Field(..., min_length=1, description="Đoạn tin hoặc claim cần kiểm chứng")
    sport_category: str | None = Field(
        default=None,
        description="Môn thể thao user chọn trước: bong_da, bong_ro, tennis, bong_chay",
    )


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


class ChatSessionSummary(BaseModel):
    """
    @brief Metadata gọn của một session để hiển thị ở sidebar.
    """

    id: str
    title: str
    sport_category: str | None = None
    category_source: str = "unknown"
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    """
    @brief Một message đã lưu trong lịch sử chat.
    """

    id: str
    session_id: str
    role: str
    message_type: str
    content: str
    payload_json: dict[str, Any] | None = None
    created_at: datetime


class ChatSessionListResponse(BaseModel):
    """
    @brief Danh sách session cho sidebar/history.
    """

    items: list[ChatSessionSummary] = Field(default_factory=list)


class CreateChatSessionResponse(BaseModel):
    """
    @brief Response khi tao mot session rong moi.
    """

    session: ChatSessionSummary


class ChatSessionDetailResponse(BaseModel):
    """
    @brief Chi tiết một session và toàn bộ message trong session đó.
    """

    session: ChatSessionSummary
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """
    @brief Response chuẩn hóa trả về cho frontend/client.
    """

    session_id: str
    message_id: str | None = None
    sport_category: str | None = None
    category_source: str = "unknown"
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


def _to_response(
    result: dict[str, Any],
    *,
    session_id: str,
    message_id: str | None = None,
    sport_category: str | None = None,
    category_source: str = "unknown",
) -> ChatResponse:
    """
    @brief Map AgentState sau khi chạy graph sang response API.
    """

    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        sport_category=sport_category,
        category_source=category_source,
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


def _serialize_session_summary(session_obj: Any) -> ChatSessionSummary:
    """
    @brief Chuẩn hóa object session ORM thành response cho sidebar.
    """

    return ChatSessionSummary(
        id=session_obj.id,
        title=session_obj.title,
        sport_category=session_obj.sport_category,
        category_source=session_obj.category_source,
        last_message_preview=session_obj.last_message_preview,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at,
    )


def _serialize_chat_message(message_obj: Any) -> ChatMessageResponse:
    """
    @brief Chuẩn hóa object message ORM thành response cho history detail.
    """

    return ChatMessageResponse(
        id=message_obj.id,
        session_id=message_obj.session_id,
        role=message_obj.role,
        message_type=message_obj.message_type,
        content=message_obj.content,
        payload_json=message_obj.payload_json,
        created_at=message_obj.created_at,
    )


def _normalize_agent_category(value: str | None) -> str:
    """
    @brief Chuẩn hóa category mà node extract trả về về bộ nhãn history.
    """

    if value is None:
        return "unknown"

    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "football": "bong_da",
        "soccer": "bong_da",
        "basketball": "bong_ro",
        "baseball": "bong_chay",
    }
    normalized = aliases.get(normalized, normalized)
    normalized = normalize_sport_category(normalized)
    return normalized or "unknown"


def _build_assistant_message_content(response: ChatResponse) -> str:
    """
    @brief Tạo content text ngắn cho assistant message lưu trong DB.
    """

    verdict = response.verdict or "UNKNOWN"
    return f"Kết luận: {verdict}"


def _build_assistant_preview(response: ChatResponse) -> str:
    """
    @brief Tạo preview ngắn cho sidebar từ response assistant.
    """

    verdict = response.verdict or "UNKNOWN"
    description = response.explanation or response.summary or verdict
    return build_last_message_preview(f"{verdict} - {description}")


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
    @brief Gọi LangGraph agent và trả về response chuẩn hóa không kèm lịch sử.
    """

    from app.agent.graph import agent

    result = await agent.ainvoke(_build_initial_state(text))
    return _to_response(result, session_id="")


async def _run_chat_with_history(req: ChatRequest) -> ChatResponse:
    """
    @brief Gọi graph, lưu lịch sử chat vào DB và trả response hoàn chỉnh cho client.
    """

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Trường 'text' không được để trống.")

    async with AsyncSessionLocal() as session:
        try:
            chat_session = None

            if req.session_id:
                chat_session = await get_chat_session(session, req.session_id)
                if chat_session is None:
                    raise HTTPException(status_code=404, detail="Không tìm thấy session.")
            else:
                requested_category = normalize_sport_category(req.sport_category)
                requested_source = "user_selected" if requested_category else "unknown"
                chat_session = await create_chat_session(
                    session,
                    title=build_session_title(text, DEFAULT_SESSION_TITLE),
                    sport_category=requested_category,
                    category_source=requested_source,
                )

            await create_chat_message(
                session,
                session_id=chat_session.id,
                role="user",
                message_type="text",
                content=text,
            )

            agent_response = await _run_agent(text)

            persisted_category = normalize_sport_category(req.sport_category) or chat_session.sport_category
            persisted_source = "user_selected" if persisted_category and req.sport_category else chat_session.category_source

            if not persisted_category:
                inferred_category = _normalize_agent_category(agent_response.category)
                persisted_category = inferred_category
                persisted_source = "inferred_from_extract" if inferred_category != "unknown" else "unknown"

            assistant_message = await create_chat_message(
                session,
                session_id=chat_session.id,
                role="assistant",
                message_type="result",
                content=_build_assistant_message_content(agent_response),
                payload_json=agent_response.model_dump(),
            )

            await update_chat_session_metadata(
                session,
                chat_session,
                title=chat_session.title or build_session_title(text, DEFAULT_SESSION_TITLE),
                sport_category=persisted_category,
                category_source=persisted_source,
                last_message_preview=_build_assistant_preview(agent_response),
            )

            await session.commit()

            payload = agent_response.model_dump()
            return _to_response(
                payload,
                session_id=chat_session.id,
                message_id=assistant_message.id,
                sport_category=persisted_category,
                category_source=persisted_source,
            )
        except HTTPException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise


async def _fetch_session_summaries(
    sport_category: str | None = None,
    search_query: str | None = None,
) -> ChatSessionListResponse:
    """
    @brief Lấy danh sách session cho sidebar, có hỗ trợ filter theo môn.
    """

    async with AsyncSessionLocal() as session:
        sessions = await list_chat_sessions(
            session,
            sport_category=sport_category,
            search_query=search_query,
        )
        return ChatSessionListResponse(items=[_serialize_session_summary(item) for item in sessions])


async def _create_empty_session() -> CreateChatSessionResponse:
    """
    @brief Tao mot session rong de frontend mo chat moi va co record that trong history.
    """

    async with AsyncSessionLocal() as session:
        chat_session = await create_chat_session(
            session,
            title=DEFAULT_SESSION_TITLE,
            sport_category=None,
            category_source="unknown",
        )
        await session.commit()
        await session.refresh(chat_session)
        return CreateChatSessionResponse(session=_serialize_session_summary(chat_session))


async def _fetch_session_detail(session_id: str) -> ChatSessionDetailResponse:
    """
    @brief Lấy metadata session và toàn bộ message của session đó.
    """

    async with AsyncSessionLocal() as session:
        session_obj = await get_chat_session(session, session_id)
        if session_obj is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy session.")

        messages = await list_chat_messages(session, session_id)
        return ChatSessionDetailResponse(
            session=_serialize_session_summary(session_obj),
            messages=[_serialize_chat_message(item) for item in messages],
        )


async def _delete_session(session_id: str) -> dict[str, bool]:
    """
    @brief Xóa một session chat khỏi DB.
    """
    async with AsyncSessionLocal() as session:
        deleted = await delete_chat_session(session, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Không tìm thấy session.")
        await session.commit()
        return {"deleted": True}


@router.get("/api/chat/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    sport_category: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    """
    @brief Endpoint lấy danh sách session cho sidebar, có thể filter theo môn thể thao.
    """

    try:
        return await _fetch_session_summaries(sport_category=sport_category, search_query=q)
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/api/chat/sessions", response_model=CreateChatSessionResponse)
async def create_empty_session():
    """
    @brief Tao mot session rong moi de frontend co the bat dau phien chat truoc khi gui message dau tien.
    """

    try:
        return await _create_empty_session()
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/api/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_session_detail(session_id: str):
    """
    @brief Endpoint lấy toàn bộ lịch sử message của một session.
    """

    try:
        return await _fetch_session_detail(session_id)
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    @brief Endpoint xóa một session và toàn bộ message của session đó.
    """
    try:
        return await _delete_session(session_id)
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    @brief Endpoint JSON để fact-check một đoạn văn bản và lưu lịch sử chat.
    """

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Trường 'text' không được để trống.")

    try:
        return await _run_chat_with_history(req)
    except HTTPException:
        raise
    except Exception as exc:
        status_code, detail = _format_runtime_error(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    @brief Endpoint SSE đơn giản, stream một kết quả hoàn chỉnh khi graph xong và đã lưu history.
    """

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Trường 'text' không được để trống.")

    async def event_generator():
        try:
            response = await _run_chat_with_history(req)
            payload = json.dumps(response.model_dump(), ensure_ascii=False, default=str)
            yield f"event: result\ndata: {payload}\n\n"
        except Exception as exc:
            _, detail = _format_runtime_error(exc)
            payload = json.dumps({"error": detail}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
