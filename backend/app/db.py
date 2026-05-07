"""
@brief Quản lý kết nối Database PostgreSQL (pgvector)
@details Khởi tạo Pool kết nối bất đồng bộ (asyncpg) phục vụ lấy dữ liệu Vector
"""

from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, Text, Column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pgvector.sqlalchemy import Vector
import os
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fakeguard")

# Tạo engine bất đồng bộ
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,           # Tự kiểm tra connection còn sống trước khi dùng
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,              # Tái tạo connection mỗi 5 phút
    connect_args={
        "server_settings": {
            "tcp_keepalives_idle": "60",
            "tcp_keepalives_interval": "10",
            "tcp_keepalives_count": "5",
        },
        "command_timeout": 300,    # Timeout 5 phút cho mỗi query
    },
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publish_date: Mapped[str] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=True, default='vi')
    label: Mapped[int] = mapped_column(Integer, default=1)   # 1 = Real, 0 = Fake
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = Column(Vector(384))

async def init_db():
    """Tạo bảng và kích hoạt extension pgvector nếu chưa có."""
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

async def get_session():
    """Dependency cung cấp session truy vấn."""
    async with AsyncSessionLocal() as session:
        yield session
