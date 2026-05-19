"""
@brief Integration test cho node extract với Groq API thật.
@details Dùng đoạn văn nhiều ý để kiểm tra LLM có tách được nhiều sub-claims
         đủ nguyên tử và có ích cho các node retrieve/judge phía sau hay không.

Yêu cầu:
  - backend/.env có GROQ_API_KEY.

Chạy:
  cd backend
  python -X utf8 test_extract_with_llm.py
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

from app.agent.nodes.extract import extract


SAMPLE_ARTICLE = """
Ban lãnh đạo Man Utd chuẩn bị đàm phán chính thức với Michael Carrick về vị trí HLV dài hạn,
với phong độ thăng hoa kể từ khi ông tiếp quản đội bóng.

Theo Telegraph ngày 13/5, Giám đốc bóng đá Jason Wilcox và CEO Omar Berrada dự kiến đề xuất
Carrick tiếp tục dẫn dắt đội một trong cuộc họp ban điều hành sắp tới. Quyết định cuối cùng
vẫn cần được đồng chủ sở hữu Jim Ratcliffe phê chuẩn, nhưng các dấu hiệu hiện tại đều cho thấy
HLV 44 tuổi sẽ được giữ lại sau khi mùa giải kết thúc.
"""


def build_state() -> dict:
    """
    @brief Tạo AgentState tối thiểu cho node extract.
    """
    return {
        "messages": [],
        "user_input": SAMPLE_ARTICLE,
        "article_text": None,
        "summary": None,
        "category": None,
        "global_entities": [],
        "sub_claims": [],
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


async def main():
    """
    @brief Gọi Groq thật để xem extract có tách sub-claims ổn không.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Thiếu GROQ_API_KEY trong backend/.env")

    print("=" * 60)
    print("TEST EXTRACT WITH REAL GROQ")
    print("=" * 60)
    print(f"Input:\n{SAMPLE_ARTICLE.strip()}\n")

    result = await extract(build_state())

    assert result["summary"], "Thiếu summary"
    assert result["category"], "Thiếu category"
    assert result["global_entities"], "Thiếu global_entities"
    assert len(result["sub_claims"]) >= 3, (
        "Đoạn văn nhiều ý như thế này nên được tách thành ít nhất 3 sub-claims."
    )
    assert result["llm_calls"] == 1, "extract phải chỉ gọi LLM đúng 1 lần"

    for idx, claim in enumerate(result["sub_claims"], 1):
        assert claim["claim"], f"Claim {idx} rỗng"
        assert claim["priority"] in {"high", "medium", "low"}, f"Claim {idx} có priority không hợp lệ"
        assert isinstance(claim["needs_web"], bool), f"Claim {idx} có needs_web không hợp lệ"

    print("Output JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nTóm tắt nhanh:")
    print(f"- Category: {result['category']}")
    print(f"- Global entities: {result['global_entities']}")
    print(f"- Số sub-claims: {len(result['sub_claims'])}")
    print("- Danh sách sub-claims:")
    for idx, claim in enumerate(result["sub_claims"], 1):
        print(f"  [{idx}] {claim['claim']}")
        print(f"      entities={claim.get('entities', [])}")
        print(f"      time_refs={claim.get('time_refs', [])}")
        print(f"      needs_web={claim.get('needs_web')}, priority={claim.get('priority')}")


if __name__ == "__main__":
    asyncio.run(main())
