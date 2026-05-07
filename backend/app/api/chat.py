from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

router = APIRouter()

class ChatRequest(BaseModel):
    """
    @brief Model định dạng dữ liệu đầu vào người dùng
    """
    message: str

@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    @brief Endpoint xử lý SSE stream trả về logic của Agent
    @details Hàm này sẽ gọi LangGraph process và yield kết quả
    """
    # Todo: Implement the streaming logic interacting directly with Agent
    pass
