"""
@brief Test script cho node summarize_and_extract
@details Chạy trực tiếp để kiểm tra chức năng tóm tắt + trích xuất sub-claims
         sử dụng Qwen qua Groq API.
"""

import asyncio
import json
import os
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Thêm backend vào path
sys.path.insert(0, os.path.dirname(__file__))

from app.agent.nodes.summarize_and_extract import summarize_and_extract


# ── Bài báo mẫu để test ──
SAMPLE_ARTICLE = """
Ngày 25/4/2026, Cristiano Ronaldo đã chính thức gia nhập câu lạc bộ Al-Nassr với mức 
lương được cho là 200 triệu euro mỗi năm theo hợp đồng có thời hạn 2 năm. Anh ấy 
trước đó đã rời Manchester United sau khi bị chấm dứt hợp đồng vào tháng 11/2022. 

Trong buổi họp báo ra mắt, cầu thủ người Bồ Đào Nha cho biết đội bóng này có 
tham vọng vô địch AFC Champions League mùa giải 2026-2027. Huấn luyện viên của 
đội bóng, ông Luis Castro, xác nhận rằng gần đây họ đã từ chối một đề nghị trị giá 
150 triệu euro từ một câu lạc bộ ở Premier League cho tiền đạo 41 tuổi.
"""


async def main():
    # Tạo state giả lập
    state = {
        "messages": [],
        "user_input": SAMPLE_ARTICLE,
        "article_text": None,
        "summary": None,
        "sub_claims": [],
        "current_idx": 0,
        "web_evidence": [],
        "kb_evidence": [],
        "final_verdict": None,
        "confidence": None,
        "explanation": None,
        "sources": [],
    }

    print("=" * 60)
    print("🧪 Test Node: summarize_and_extract")
    print("=" * 60)
    print(f"\n📰 Input ({len(SAMPLE_ARTICLE.strip())} ký tự):")
    print(SAMPLE_ARTICLE.strip()[:200] + "...")

    print("\n⏳ Đang gọi LLM (Qwen qua Groq)...\n")

    result = await summarize_and_extract(state)

    print("✅ KẾT QUẢ:")
    print("-" * 60)
    print(json.dumps(
        {
            "summary": result["summary"],
            "claims": [sc["claim"] for sc in result["sub_claims"]],
        },
        ensure_ascii=False,
        indent=2,
    ))
    print("-" * 60)

    # Kiểm tra cấu trúc
    assert "summary" in result, "Thiếu key 'summary'"
    assert "sub_claims" in result, "Thiếu key 'sub_claims'"
    assert len(result["sub_claims"]) >= 2, f"Cần ít nhất 2 claims, nhận {len(result['sub_claims'])}"
    assert result["current_idx"] == 0, "current_idx phải reset về 0"

    for i, sc in enumerate(result["sub_claims"]):
        assert sc["claim"], f"Claim {i} trống"
        assert sc["verdict"] is None, f"Claim {i} verdict phải là None"
        print(f"  ✓ Claim {i+1}: {sc['claim']}")

    print(f"\n🎉 Tất cả {len(result['sub_claims'])} claims đều hợp lệ!")


if __name__ == "__main__":
    asyncio.run(main())
