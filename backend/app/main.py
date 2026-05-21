import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.db import init_db


load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    @brief Khởi tạo bảng cần thiết khi FastAPI startup.
    """
    if os.getenv("FAKEGUARD_SKIP_DB_INIT", "0") != "1":
        await init_db()
    yield


app = FastAPI(
    title="FakeGuard API",
    description="API kiểm chứng tin giả tiếng Việt dùng RAG Agentic",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
