"""
@brief Integration test cho node retrieve_internal với PostgreSQL + pgvector thật.
@details Test này kiểm tra retriever có thực sự embed query, truy vấn database và
         trả về evidence từ bảng knowledge_base hay không.

Yêu cầu trước khi chạy:
  1. Docker PostgreSQL/pgvector đang chạy.
  2. DATABASE_URL trong .env trỏ đúng DB.
  3. DB đã được seed bằng backend/scripts/seed_kb.py.

Chạy:
  python -X utf8 test_rag.py
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from app.agent.nodes.retrieve_internal import retrieve_internal


SAMPLE_STATE = {
    "messages": [],
    "user_input": "",
    "article_text": None,
    "summary": "Kiểm tra truy xuất nội bộ với dữ liệu bóng đá Ligue 1.",
    "category": "bong-da",
    "global_entities": ["Ligue 1", "Pháp", "vua phá lưới"],
    "sub_claims": [
        {
            "claim": "Danh sách top ghi bàn vua phá lưới bóng đá Pháp Ligue 1 mùa 2025/2026 được công bố.",
            "entities": ["Ligue 1", "bóng đá Pháp", "vua phá lưới"],
            "time_refs": ["2025/2026"],
            "needs_web": False,
            "priority": "medium",
            "kb_evidence": None,
            "web_evidence": None,
            "verdict": None,
            "confidence": None,
            "reasoning": None,
            "evidence": None,
        }
    ],
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


def _print_requirements_on_failure(exc: Exception) -> None:
    """
    @brief In hướng dẫn ngắn khi integration test không kết nối/truy xuất được DB.
    """
    print("\nKhông chạy được integration test retrieval.")
    print("Kiểm tra các điều kiện sau:")
    print("  - Docker DB đang chạy: docker compose up -d db")
    print("  - DATABASE_URL đúng trong backend/.env")
    print("  - Đã seed dữ liệu: cd backend && python -X utf8 scripts/seed_kb.py")
    print(f"\nLỗi gốc: {type(exc).__name__}: {exc}")


async def main():
    try:
        result = await retrieve_internal(SAMPLE_STATE, top_k=5)
    except Exception as exc:
        _print_requirements_on_failure(exc)
        raise

    claims = result.get("sub_claims", [])
    assert len(claims) == 1, "retrieve_internal phải giữ nguyên số claim"

    evidence = claims[0].get("kb_evidence")
    assert isinstance(evidence, list), "kb_evidence phải là list"
    assert evidence, (
        "Retriever không trả evidence nào từ DB. "
        "Nếu DB đã seed, hãy kiểm tra category/query/entity hoặc dữ liệu knowledge_base."
    )

    first = evidence[0]
    required_keys = {"id", "title", "domain", "url", "content", "match_source"}
    missing = required_keys - set(first)
    assert not missing, f"Evidence thiếu key: {missing}"
    assert first["title"], "Evidence đầu tiên thiếu title"
    assert first["content"], "Evidence đầu tiên thiếu content"
    assert first["match_source"] in {"vector", "keyword", "keyword+vector"}, "match_source không hợp lệ"

    print("=" * 60)
    print("TEST INTERNAL RAG RETRIEVER WITH REAL DB")
    print("=" * 60)
    print(f"Tìm được {len(evidence)} evidence từ knowledge_base.\n")
    for idx, item in enumerate(evidence, 1):
        print(f"[{idx}] {item['title']}")
        print(f"    URL: {item['url']}")
        print(f"    Domain: {item['domain']} | Match: {item['match_source']} | Entity hits: {item['entity_hits']}")
        print()

    print("JSON preview:")
    print(json.dumps({"sub_claims": claims}, ensure_ascii=False, indent=2)[:3000])
    print("\nRetriever đã truy vấn DB thật và trả về evidence hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
