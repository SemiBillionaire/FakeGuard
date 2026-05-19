"""
@brief Unit test cho node extract.
@details Test không gọi API thật; monkeypatch LLM bằng fake response để kiểm tra
         parser, normalize schema và state update.
"""

import asyncio
import json
import os
import sys
import importlib
from types import SimpleNamespace

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

extract_module = importlib.import_module("app.agent.nodes.extract")


SAMPLE_ARTICLE = """
Ngày 25/4/2026, Cristiano Ronaldo được cho là đã ký hợp đồng hai năm với Al-Nassr,
nhận lương 200 triệu euro mỗi năm. Bài viết cũng nói Al-Nassr muốn vô địch AFC
Champions League mùa 2026-2027.
"""


FAKE_EXTRACT_RESPONSE = {
    "summary": "Bài viết nói Cristiano Ronaldo ký hợp đồng mới với Al-Nassr và đội bóng đặt mục tiêu vô địch AFC Champions League.",
    "category": "bong-da",
    "global_entities": ["Cristiano Ronaldo", "Al-Nassr", "AFC Champions League"],
    "claims": [
        {
            "claim": "Cristiano Ronaldo ký hợp đồng hai năm với Al-Nassr vào ngày 25/4/2026.",
            "entities": ["Cristiano Ronaldo", "Al-Nassr"],
            "time_refs": ["25/4/2026"],
            "needs_web": True,
            "priority": "high",
        },
        {
            "claim": "Cristiano Ronaldo nhận lương 200 triệu euro mỗi năm tại Al-Nassr.",
            "entities": ["Cristiano Ronaldo", "Al-Nassr"],
            "time_refs": [],
            "needs_web": True,
            "priority": "high",
        },
        {
            "claim": "Al-Nassr muốn vô địch AFC Champions League mùa 2026-2027.",
            "entities": ["Al-Nassr", "AFC Champions League"],
            "time_refs": ["mùa 2026-2027"],
            "needs_web": False,
            "priority": "medium",
        },
    ],
}


class FakeLLM:
    """
    @brief Fake LLM trả về JSON cố định để unit test không phụ thuộc network/API.
    """

    async def ainvoke(self, _messages):
        return SimpleNamespace(content=json.dumps(FAKE_EXTRACT_RESPONSE, ensure_ascii=False))


async def main():
    original_get_llm = extract_module._get_llm
    extract_module._get_llm = lambda: FakeLLM()

    try:
        state = {
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

        result = await extract_module.extract(state)
    finally:
        extract_module._get_llm = original_get_llm

    assert result["summary"], "Thiếu summary"
    assert result["category"] == "bong-da", "Sai category"
    assert "Cristiano Ronaldo" in result["global_entities"], "Thiếu global entity"
    assert result["current_idx"] == 0, "current_idx phải reset về 0"
    assert result["llm_calls"] == 1, "llm_calls phải tăng thêm 1"
    assert len(result["sub_claims"]) == 3, "Số claim không đúng"

    for claim in result["sub_claims"]:
        assert claim["claim"], "Claim rỗng"
        assert isinstance(claim["entities"], list), "entities phải là list"
        assert isinstance(claim["time_refs"], list), "time_refs phải là list"
        assert isinstance(claim["needs_web"], bool), "needs_web phải là bool"
        assert claim["priority"] in {"high", "medium", "low"}, "priority không hợp lệ"
        assert claim["kb_evidence"] is None, "kb_evidence mặc định phải là None"
        assert claim["web_evidence"] is None, "web_evidence mặc định phải là None"
        assert claim["verdict"] is None, "verdict mặc định phải là None"

    lebron_category = extract_module._infer_category_from_text(
        "LeBron James thông báo giải nghệ sau trận thua OKC ở game 4 playoff NBA 2026."
    )
    assert lebron_category == "bong-ro", "LeBron/OKC/NBA phải được phân loại là bóng rổ"
    assert (
        extract_module._normalize_known_entities("Giannis Antetokunmpo sẽ rời Bucks")
        == "Giannis Antetokounmpo sẽ rời Bucks"
    ), "Phải sửa được typo phổ biến Antetokounmpo"
    assert (
        extract_module._normalize_known_entities("Griezmamn thay Lewandoski")
        == "Antoine Griezmann thay Robert Lewandowski"
    ), "Phải chuẩn hóa được Griezmann/Lewandowski"

    print("=" * 60)
    print("TEST EXTRACT NODE")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nTất cả assertion cho extract node đều hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
