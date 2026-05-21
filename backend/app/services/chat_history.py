"""
@brief Service CRUD cho lịch sử chat.
@details Cung cấp các hàm khung để tạo session, lưu message và đọc sidebar history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ChatMessage, ChatSession


SPORT_CATEGORIES = {"bong_da", "bong_ro", "tennis", "bong_chay", "unknown"}
CATEGORY_SOURCES = {"user_selected", "inferred_from_extract", "unknown"}
MESSAGE_ROLES = {"user", "assistant"}
MESSAGE_TYPES = {"text", "result", "error"}


def _utc_now() -> datetime:
    """
    @brief Trả về thời gian UTC hiện tại để cập nhật metadata session.
    """
    return datetime.now(timezone.utc)


def normalize_sport_category(value: str | None) -> str | None:
    """
    @brief Chuẩn hóa category môn thể thao đầu vào trước khi lưu DB.
    """
    if value is None:
        return None

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    aliases = {
        "football": "bong_da",
        "soccer": "bong_da",
        "basketball": "bong_ro",
        "baseball": "bong_chay",
    }
    normalized = aliases.get(normalized, normalized)

    return normalized if normalized in SPORT_CATEGORIES else "unknown"


def normalize_category_source(value: str | None) -> str:
    """
    @brief Chuẩn hóa nguồn xác định category.
    """
    if value is None:
        return "unknown"

    normalized = value.strip().lower()
    return normalized if normalized in CATEGORY_SOURCES else "unknown"


def build_session_title(text: str, fallback: str = "Cuộc trò chuyện mới") -> str:
    """
    @brief Sinh title ngắn gọn từ message đầu tiên của người dùng.
    """
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return fallback
    return cleaned[:80].rstrip()


def build_last_message_preview(content: str, limit: int = 120) -> str:
    """
    @brief Tạo preview ngắn để hiển thị trong sidebar.
    """
    cleaned = " ".join((content or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


async def create_chat_session(
    session: AsyncSession,
    *,
    title: str | None = None,
    sport_category: str | None = None,
    category_source: str = "unknown",
    last_message_preview: str | None = None,
) -> ChatSession:
    """
    @brief Tạo một phiên chat mới trong DB.
    """
    chat_session = ChatSession(
        title=title or "Cuộc trò chuyện mới",
        sport_category=normalize_sport_category(sport_category),
        category_source=normalize_category_source(category_source),
        last_message_preview=last_message_preview,
    )
    session.add(chat_session)
    await session.flush()
    return chat_session


async def get_chat_session(session: AsyncSession, session_id: str) -> ChatSession | None:
    """
    @brief Lấy một session theo id.
    """
    return await session.get(ChatSession, session_id)


async def list_chat_sessions(
    session: AsyncSession,
    *,
    sport_category: str | None = None,
    search_query: str | None = None,
    limit: int = 50,
) -> list[ChatSession]:
    """
    @brief Lấy danh sách session để render sidebar, ưu tiên session mới cập nhật.
    """
    stmt: Select[tuple[ChatSession]] = select(ChatSession).order_by(ChatSession.updated_at.desc())

    normalized_category = normalize_sport_category(sport_category)
    if normalized_category and normalized_category != "unknown":
        stmt = stmt.where(ChatSession.sport_category == normalized_category)

    cleaned_query = " ".join((search_query or "").split()).strip()
    if cleaned_query:
        pattern = f"%{cleaned_query}%"
        stmt = (
            stmt.outerjoin(
                ChatMessage,
                and_(
                    ChatMessage.session_id == ChatSession.id,
                    ChatMessage.role == "user",
                ),
            )
            .where(
                or_(
                    ChatSession.title.ilike(pattern),
                    ChatSession.last_message_preview.ilike(pattern),
                    ChatMessage.content.ilike(pattern),
                )
            )
            .distinct()
        )

    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_chat_messages(session: AsyncSession, session_id: str) -> list[ChatMessage]:
    """
    @brief Lấy toàn bộ message của một session theo thứ tự thời gian.
    """
    stmt: Select[tuple[ChatMessage]] = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_chat_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    message_type: str,
    content: str,
    payload_json: dict[str, Any] | None = None,
) -> ChatMessage:
    """
    @brief Lưu một message mới cho session.
    """
    normalized_role = role.strip().lower()
    normalized_type = message_type.strip().lower()

    if normalized_role not in MESSAGE_ROLES:
        raise ValueError(f"Invalid message role: {role}")
    if normalized_type not in MESSAGE_TYPES:
        raise ValueError(f"Invalid message type: {message_type}")

    message = ChatMessage(
        session_id=session_id,
        role=normalized_role,
        message_type=normalized_type,
        content=content,
        payload_json=payload_json,
    )
    session.add(message)
    await session.flush()
    return message


async def update_chat_session_metadata(
    session: AsyncSession,
    chat_session: ChatSession,
    *,
    title: str | None = None,
    sport_category: str | None = None,
    category_source: str | None = None,
    last_message_preview: str | None = None,
) -> ChatSession:
    """
    @brief Cập nhật metadata session sau khi lưu message hoặc có category mới.
    """
    if title is not None:
        chat_session.title = title

    if sport_category is not None:
        chat_session.sport_category = normalize_sport_category(sport_category)

    if category_source is not None:
        chat_session.category_source = normalize_category_source(category_source)

    if last_message_preview is not None:
        chat_session.last_message_preview = last_message_preview

    chat_session.updated_at = _utc_now()
    await session.flush()
    return chat_session


async def delete_chat_session(session: AsyncSession, session_id: str) -> bool:
    """
    @brief Xóa một session và toàn bộ message liên quan.
    """
    chat_session = await get_chat_session(session, session_id)
    if chat_session is None:
        return False

    await session.delete(chat_session)
    await session.flush()
    return True
