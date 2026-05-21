"""
@brief Quản lý kết nối Database PostgreSQL (pgvector)
@details Khởi tạo pool kết nối bất đồng bộ (asyncpg) và định nghĩa các model dùng chung.
"""

from datetime import datetime, timezone
import os
from uuid import uuid4

from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fakeguard")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args={
        "server_settings": {
            "tcp_keepalives_idle": "60",
            "tcp_keepalives_interval": "10",
            "tcp_keepalives_count": "5",
        },
        "command_timeout": 300,
    },
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


def _utc_now() -> datetime:
    """
    @brief Trả về mốc thời gian UTC hiện tại.
    """
    return datetime.now(timezone.utc)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publish_date: Mapped[str] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=True, default="vi")
    label: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = Column(Vector(384))


class ChatSession(Base):
    """
    @brief Lưu metadata của một phiên chat để render sidebar và truy vết lịch sử.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="Cuộc trò chuyện mới")
    sport_category: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    category_source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """
    @brief Lưu từng message trong một phiên chat, gồm cả user và assistant.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


async def init_db():
    """
    @brief Tạo bảng và kích hoạt extension pgvector nếu chưa có.
    """
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE IF EXISTS chat_sessions ALTER COLUMN sport_category TYPE VARCHAR(32)"))
        await conn.execute(text("ALTER TABLE IF EXISTS chat_sessions ALTER COLUMN category_source TYPE VARCHAR(32)"))


async def get_session():
    """
    @brief Dependency cung cấp session truy vấn.
    """
    async with AsyncSessionLocal() as session:
        yield session
