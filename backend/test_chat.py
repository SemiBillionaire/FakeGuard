import asyncio
import os
import sys

from fastapi.testclient import TestClient

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(__file__)
sys.path.insert(0, BACKEND_DIR)

from app.main import app
import app.api.chat as chat_module


client = TestClient(app)


async def fake_run_agent(_text: str):
    return chat_module.ChatResponse(
        verdict="REFUTED",
        confidence=0.91,
        summary="Tóm tắt mẫu",
        explanation="Giải thích mẫu",
        category="bong-da",
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


async def fake_rate_limit(_text: str):
    raise RuntimeError("Rate limit reached for model")


def main():
    original_run_agent = chat_module._run_agent

    try:
        chat_module._run_agent = fake_run_agent

        ok_response = client.post("/api/chat", json={"text": "Claim cần kiểm chứng"})
        assert ok_response.status_code == 200, ok_response.text
        ok_payload = ok_response.json()
        assert ok_payload["verdict"] == "REFUTED"
        assert ok_payload["confidence"] == 0.91
        assert ok_payload["claims"][0]["claim"] == "Claim mẫu"
        assert ok_payload["sources"][0]["url"] == "https://example.com/source"

        bad_request = client.post("/api/chat", json={"text": "   "})
        assert bad_request.status_code == 400, bad_request.text

        stream_response = client.post("/api/chat/stream", json={"text": "Claim stream"})
        assert stream_response.status_code == 200, stream_response.text
        assert "event: result" in stream_response.text
        assert '"verdict": "REFUTED"' in stream_response.text

        chat_module._run_agent = fake_rate_limit
        limited = client.post("/api/chat", json={"text": "Claim rate limit"})
        assert limited.status_code == 429, limited.text
        assert "rate limit" in limited.json()["detail"].lower()

        stream_error = client.post("/api/chat/stream", json={"text": "Claim stream error"})
        assert stream_error.status_code == 200, stream_error.text
        assert "event: error" in stream_error.text
        assert "rate limit" in stream_error.text.lower()
    finally:
        chat_module._run_agent = original_run_agent

    print("Tất cả assertion cho chat API đều hợp lệ.")


if __name__ == "__main__":
    main()
