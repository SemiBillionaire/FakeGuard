"""
@brief Unit test cho node search_web.
@details Test monkeypatch Tavily wrapper để không gọi API thật, tập trung kiểm tra
         routing claim NEI/needs_web và cập nhật web_evidence.
"""

import asyncio
import importlib
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

search_web_module = importlib.import_module("app.agent.nodes.search_web")


FAKE_WEB_RESULTS = {
    "Cristiano Ronaldo ký hợp đồng hai năm với Al-Nassr vào ngày 25/4/2026.": [
        {
            "title": "Ronaldo contract status report",
            "url": "https://example.com/ronaldo-contract",
            "content": "No new Al-Nassr contract was signed on April 25, 2026.",
            "score": 0.92,
            "domain": "example.com",
        }
    ],
    "Al-Nassr muốn vô địch AFC Champions League mùa 2026-2027.": [
        {
            "title": "Al-Nassr AFC Champions League ambition",
            "url": "https://example.com/al-nassr-afc",
            "content": "Al-Nassr officials discussed AFC Champions League ambitions.",
            "score": 0.84,
            "domain": "example.com",
        }
    ],
}


async def fake_search_claim_web(claim, category, max_results, search_depth):
    """
    @brief Fake Tavily call để kiểm tra tham số truyền xuống từ node.
    """
    assert category == "bong-da", "category truyền xuống Tavily không đúng"
    assert max_results == 3, "max_results mặc định phải là 3"
    assert search_depth == "basic", "search_depth mặc định phải là basic"
    return FAKE_WEB_RESULTS.get(claim["claim"], [])


def build_state():
    """
    @brief Tạo state gồm 3 claim: SUPPORTED, NEI và needs_web=True.
    """
    return {
        "messages": [],
        "user_input": "",
        "article_text": None,
        "summary": "Bài viết gồm các claim cần kiểm chứng web.",
        "category": "bong-da",
        "global_entities": ["Cristiano Ronaldo", "Al-Nassr"],
        "sub_claims": [
            {
                "claim": "Danh sách top ghi bàn Ligue 1 mùa 2025/2026 được công bố.",
                "entities": ["Ligue 1"],
                "time_refs": ["2025/2026"],
                "needs_web": False,
                "priority": "medium",
                "kb_evidence": [{"title": "Top ghi bàn Ligue 1", "url": "https://example.com/ligue1"}],
                "web_evidence": None,
                "verdict": "SUPPORTED",
                "confidence": 0.86,
                "reasoning": "Đã đủ bằng chứng nội bộ.",
                "evidence": [{"title": "Top ghi bàn Ligue 1", "url": "https://example.com/ligue1"}],
            },
            {
                "claim": "Cristiano Ronaldo ký hợp đồng hai năm với Al-Nassr vào ngày 25/4/2026.",
                "entities": ["Cristiano Ronaldo", "Al-Nassr"],
                "time_refs": ["25/4/2026"],
                "needs_web": True,
                "priority": "high",
                "kb_evidence": [],
                "web_evidence": None,
                "verdict": "NEI",
                "confidence": 0.25,
                "reasoning": "Kho nội bộ chưa đủ bằng chứng.",
                "evidence": [],
            },
            {
                "claim": "Al-Nassr muốn vô địch AFC Champions League mùa 2026-2027.",
                "entities": ["Al-Nassr", "AFC Champions League"],
                "time_refs": ["mùa 2026-2027"],
                "needs_web": True,
                "priority": "medium",
                "kb_evidence": [],
                "web_evidence": None,
                "verdict": None,
                "confidence": None,
                "reasoning": None,
                "evidence": None,
            },
        ],
        "current_idx": 0,
        "web_evidence": [],
        "kb_evidence": [],
        "final_verdict": None,
        "confidence": None,
        "explanation": None,
        "sources": [],
        "llm_calls": 2,
        "tavily_calls": 0,
    }


async def main():
    original_search = search_web_module._search_claim_web
    search_web_module._search_claim_web = fake_search_claim_web

    try:
        state = build_state()
        result = await search_web_module.search_web(state)
    finally:
        search_web_module._search_claim_web = original_search

    claims = result["sub_claims"]
    assert result["tavily_calls"] == 2, "Chỉ 2 claim cần gọi Tavily"
    assert claims[0]["web_evidence"] is None, "Claim SUPPORTED không được gọi Tavily"
    assert claims[1]["web_evidence"], "Claim NEI phải có web_evidence"
    assert claims[2]["web_evidence"], "Claim needs_web=True phải có web_evidence"
    assert claims[1]["web_evidence"][0]["url"] == "https://example.com/ronaldo-contract"
    assert claims[2]["web_evidence"][0]["domain"] == "example.com"
    assert claims[1]["verdict"] == "NEI", "search_web không được tự judge verdict"

    print("=" * 60)
    print("TEST SEARCH_WEB NODE")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nTất cả assertion cho search_web node đều hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
