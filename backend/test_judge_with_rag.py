"""
@brief Integration test: retrieve_internal + judge_internal với DB thật và Groq API thật.
@details Test này dùng PostgreSQL/pgvector để lấy evidence, sau đó gọi Groq để judge
         xem LLM có kết luận đúng dựa trên evidence từ các bài báo hay không.

Yêu cầu trước khi chạy:
  1. Docker PostgreSQL/pgvector đang chạy.
  2. DB đã được seed bằng backend/scripts/seed_kb.py.
  3. backend/.env có DATABASE_URL và GROQ_API_KEY.

Chạy:
  cd backend
  python -X utf8 test_judge_with_rag.py
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))
sys.path.insert(0, BACKEND_DIR)

from app.agent.nodes.judge import judge_internal
from app.agent.nodes.retrieve_internal import retrieve_internal


def build_state() -> dict:
    """
    @brief Tạo state mẫu bám sát dữ liệu chắc chắn có trong real_news.csv.
    @details Claim này được chọn vì test_rag.py đã xác nhận DB trả evidence liên quan.
    """
    return {
        "messages": [],
        "user_input": "",
        "article_text": None,
        "summary": "Kiểm tra LLM judge dựa trên evidence nội bộ về Ligue 1.",
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


def assert_env_ready() -> None:
    """
    @brief Kiểm tra biến môi trường bắt buộc trước khi gọi DB/LLM.
    """
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("Thiếu DATABASE_URL trong backend/.env")
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Thiếu GROQ_API_KEY trong backend/.env")


def print_evidence(claim: dict) -> None:
    """
    @brief In evidence mà retriever tìm được để người dùng đánh giá retrieval.
    """
    evidence = claim.get("kb_evidence") or []
    print(f"\nEvidence từ DB ({len(evidence)} kết quả):")
    for idx, item in enumerate(evidence, 1):
        print(f"[{idx}] {item.get('title')}")
        print(f"    URL: {item.get('url')}")
        print(
            "    "
            f"Domain: {item.get('domain')} | "
            f"Match: {item.get('match_source')} | "
            f"Entity hits: {item.get('entity_hits')}"
        )
        preview = str(item.get("content") or "").replace("\n", " ")[:220]
        print(f"    Content: {preview}...")
        print()


def print_judgment(claim: dict) -> None:
    """
    @brief In verdict của LLM sau judge_internal.
    """
    print("\nKết quả judge_internal từ Groq:")
    print(f"Claim: {claim.get('claim')}")
    print(f"Verdict: {claim.get('verdict')}")
    print(f"Confidence: {claim.get('confidence')}")
    print(f"Needs web: {claim.get('needs_web')}")
    print(f"Reasoning: {claim.get('reasoning')}")
    print("\nEvidence LLM chọn:")
    print(json.dumps(claim.get("evidence") or [], ensure_ascii=False, indent=2))


async def main():
    assert_env_ready()

    state = build_state()
    print("=" * 60)
    print("TEST JUDGE WITH REAL RAG + GROQ")
    print("=" * 60)
    print(f"Claim đầu vào: {state['sub_claims'][0]['claim']}")

    try:
        retrieve_result = await retrieve_internal(state, top_k=5)
    except Exception as exc:
        print("\nKhông retrieve được evidence từ DB.")
        print("Kiểm tra Docker DB, DATABASE_URL và dữ liệu đã seed.")
        raise exc

    state_after_retrieve = {**state, **retrieve_result}
    retrieved_claim = state_after_retrieve["sub_claims"][0]
    evidence = retrieved_claim.get("kb_evidence") or []
    assert evidence, "Retriever không trả evidence nào; không thể test judge với RAG."
    print_evidence(retrieved_claim)

    judge_result = await judge_internal(state_after_retrieve)
    judged_claim = judge_result["sub_claims"][0]

    assert judged_claim.get("verdict") in {"SUPPORTED", "REFUTED", "NEI"}, "Verdict không hợp lệ"
    assert isinstance(judged_claim.get("confidence"), float), "Confidence phải là float"
    assert judged_claim.get("reasoning"), "Judge phải trả reasoning"
    assert judge_result.get("llm_calls") == 1, "judge_internal phải tăng llm_calls từ 0 lên 1"

    print_judgment(judged_claim)
    print("\nJSON output đầy đủ:")
    print(json.dumps(judge_result, ensure_ascii=False, indent=2))

    print("\nTest hoàn tất: retriever đã lấy DB thật và Groq đã judge trên evidence đó.")


if __name__ == "__main__":
    asyncio.run(main())
