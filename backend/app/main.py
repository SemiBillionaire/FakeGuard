from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router

"""
@brief Khởi tạo ứng dụng FastAPI cho FakeGuard
@details Cấu hình CORS middleware cho phép gọi từ Frontend (Vite)
"""
app = FastAPI(title="FakeGuard API", description="API kiểm chứng tin giả tiếng Việt dùng RAG Agentic")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"], 
    allow_headers=["*"],
)

app.include_router(chat_router)
