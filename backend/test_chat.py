import os
import sys
from datetime import datetime, timezone

from fastapi.testclient import TestClient

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(__file__)
sys.path.insert(0, BACKEND_DIR)
os.environ["FAKEGUARD_SKIP_DB_INIT"] = "1"

from app.main import app
import app.api.chat as chat_module


client = TestClient(app)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def fake_run_chat_with_history(req: chat_module.ChatRequest):
    return chat_module.ChatResponse(
        session_id=req.session_id or "session-demo-1",
        message_id="assistant-message-1",
        sport_category=req.sport_category or "bong_da",
        category_source="user_selected" if req.sport_category else "inferred_from_extract",
        verdict="REFUTED",
        confidence=0.91,
        summary="Tóm tắt mẫu",
        explanation="Giải thích mẫu",
        category="bong_da",
        claims=[
            chat_module.ClaimResponse(
                claim="Claim mẫu",
                verdict="REFUTED",
                confidence=0.91,
                reasoning="Lý do mẫu",
                entities=["Barcelona"],
                time_refs=["2026"],
            )
        ],
        sources=[
            chat_module.SourceResponse(
                title="Nguồn mẫu",
                url="https://example.com/source",
                relevance="Liên quan trực tiếp",
                claim="Claim mẫu",
                verdict="REFUTED",
            )
        ],
        llm_calls=2,
        tavily_calls=1,
    )


async def fake_fetch_sessions(sport_category: str | None = None, search_query: str | None = None):
    return chat_module.ChatSessionListResponse(
        items=[
            chat_module.ChatSessionSummary(
                id="session-demo-1",
                title=f"Barcelona chính thức kí lại hợp đồng... {search_query or ''}".strip(),
                sport_category=sport_category or "bong_da",
                category_source="user_selected",
                last_message_preview="REFUTED - Không có bằng chứng...",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
        ]
    )


async def fake_create_empty_session():
    return chat_module.CreateChatSessionResponse(
        session=chat_module.ChatSessionSummary(
            id="session-empty-1",
            title="Cuộc trò chuyện mới",
            sport_category=None,
            category_source="unknown",
            last_message_preview=None,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )


async def fake_fetch_session_detail(session_id: str):
    return chat_module.ChatSessionDetailResponse(
        session=chat_module.ChatSessionSummary(
            id=session_id,
            title="Barcelona chính thức kí lại hợp đồng...",
            sport_category="bong_da",
            category_source="user_selected",
            last_message_preview="REFUTED - Không có bằng chứng...",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        ),
        messages=[
            chat_module.ChatMessageResponse(
                id="user-message-1",
                session_id=session_id,
                role="user",
                message_type="text",
                content="Barcelona chính thức kí lại hợp đồng với Griezmann",
                payload_json=None,
                created_at=_utc_now(),
            ),
            chat_module.ChatMessageResponse(
                id="assistant-message-1",
                session_id=session_id,
                role="assistant",
                message_type="result",
                content="Kết luận: REFUTED",
                payload_json={"verdict": "REFUTED", "confidence": 0.91},
                created_at=_utc_now(),
            ),
        ],
    )


async def fake_delete_session(_session_id: str):
    return {"deleted": True}


async def fake_rate_limit(_req: chat_module.ChatRequest):
    raise RuntimeError("Rate limit reached for model")


def main():
    original_run_chat_with_history = chat_module._run_chat_with_history
    original_fetch_sessions = chat_module._fetch_session_summaries
    original_create_empty_session = chat_module._create_empty_session
    original_fetch_session_detail = chat_module._fetch_session_detail
    original_delete_session = chat_module._delete_session

    try:
        chat_module._run_chat_with_history = fake_run_chat_with_history
        chat_module._fetch_session_summaries = fake_fetch_sessions
        chat_module._create_empty_session = fake_create_empty_session
        chat_module._fetch_session_detail = fake_fetch_session_detail
        chat_module._delete_session = fake_delete_session

        ok_response = client.post(
            "/api/chat",
            json={"text": "Claim cần kiểm chứng", "sport_category": "bong_da"},
        )
        assert ok_response.status_code == 200, ok_response.text
        ok_payload = ok_response.json()
        assert ok_payload["session_id"] == "session-demo-1"
        assert ok_payload["message_id"] == "assistant-message-1"
        assert ok_payload["sport_category"] == "bong_da"
        assert ok_payload["verdict"] == "REFUTED"
        assert ok_payload["confidence"] == 0.91
        assert ok_payload["claims"][0]["claim"] == "Claim mẫu"
        assert ok_payload["sources"][0]["url"] == "https://example.com/source"

        bad_request = client.post("/api/chat", json={"text": "   "})
        assert bad_request.status_code == 400, bad_request.text

        sessions_response = client.get("/api/chat/sessions?sport_category=bong_da&q=griezmann")
        assert sessions_response.status_code == 200, sessions_response.text
        sessions_payload = sessions_response.json()
        assert sessions_payload["items"][0]["id"] == "session-demo-1"
        assert sessions_payload["items"][0]["sport_category"] == "bong_da"
        assert "griezmann" in sessions_payload["items"][0]["title"].lower()

        create_response = client.post("/api/chat/sessions")
        assert create_response.status_code == 200, create_response.text
        create_payload = create_response.json()
        assert create_payload["session"]["id"] == "session-empty-1"
        assert create_payload["session"]["title"] == "Cuộc trò chuyện mới"

        detail_response = client.get("/api/chat/sessions/session-demo-1")
        assert detail_response.status_code == 200, detail_response.text
        detail_payload = detail_response.json()
        assert detail_payload["session"]["id"] == "session-demo-1"
        assert detail_payload["messages"][0]["role"] == "user"
        assert detail_payload["messages"][1]["message_type"] == "result"

        delete_response = client.delete("/api/chat/sessions/session-demo-1")
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json()["deleted"] is True

        stream_response = client.post("/api/chat/stream", json={"text": "Claim stream"})
        assert stream_response.status_code == 200, stream_response.text
        assert "event: result" in stream_response.text
        assert '"verdict": "REFUTED"' in stream_response.text

        chat_module._run_chat_with_history = fake_rate_limit
        limited = client.post("/api/chat", json={"text": "Claim rate limit"})
        assert limited.status_code == 429, limited.text
        assert "rate limit" in limited.json()["detail"].lower()

        stream_error = client.post("/api/chat/stream", json={"text": "Claim stream error"})
        assert stream_error.status_code == 200, stream_error.text
        assert "event: error" in stream_error.text
        assert "rate limit" in stream_error.text.lower()
    finally:
        chat_module._run_chat_with_history = original_run_chat_with_history
        chat_module._fetch_session_summaries = original_fetch_sessions
        chat_module._create_empty_session = original_create_empty_session
        chat_module._fetch_session_detail = original_fetch_session_detail
        chat_module._delete_session = original_delete_session

    print("Tất cả assertion cho chat API đều hợp lệ.")


if __name__ == "__main__":
    main()
