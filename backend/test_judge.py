"""
@brief Unit test cho node judge_internal và judge_after_web.
@details Test monkeypatch LLM bằng fake responses để kiểm tra parse JSON,
         cập nhật verdict và chỉ judge lại claim NEI sau khi có web evidence.
"""

import asyncio
import importlib
import json
import os
import sys
from types import SimpleNamespace

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

judge_module = importlib.import_module("app.agent.nodes.judge")


INTERNAL_RESPONSE = {
    "claims": [
        {
            "idx": 0,
            "verdict": "SUPPORTED",
            "confidence": 0.86,
            "reasoning": "Bằng chứng nội bộ xác nhận bài về top ghi bàn Ligue 1 mùa 2025/2026.",
            "needs_web": False,
            "evidence": [
                {
                    "title": "Top ghi bàn vua phá lưới bóng đá Pháp Ligue 1 2025/2026",
                    "url": "https://example.com/ligue-1-scorers",
                    "relevance": "Nguồn nêu đúng danh sách top ghi bàn Ligue 1 2025/2026.",
                }
            ],
        },
        {
            "idx": 1,
            "verdict": "NEI",
            "confidence": 0.25,
            "reasoning": "Bằng chứng nội bộ chưa đủ để kết luận về hợp đồng của Ronaldo.",
            "needs_web": True,
            "evidence": [],
        },
    ]
}


WEB_RESPONSE = {
    "claims": [
        {
            "idx": 1,
            "verdict": "REFUTED",
            "confidence": 0.91,
            "reasoning": "Bằng chứng web mâu thuẫn với claim về hợp đồng ngày 25/4/2026.",
            "needs_web": False,
            "evidence": [
                {
                    "title": "Ronaldo contract status report",
                    "url": "https://example.com/ronaldo-contract",
                    "relevance": "Nguồn cho biết không có hợp đồng mới ngày 25/4/2026.",
                }
            ],
        }
    ]
}


class FakeLLM:
    """
    @brief Fake LLM trả response lần lượt cho judge_internal và judge_after_web.
    """

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        response = INTERNAL_RESPONSE if self.calls == 1 else WEB_RESPONSE
        return SimpleNamespace(content=json.dumps(response, ensure_ascii=False))


def build_state():
    """
    @brief Tạo AgentState mẫu có 2 claim, một claim đủ KB và một claim cần web.
    """
    return {
        "messages": [],
        "user_input": "",
        "article_text": None,
        "summary": "Bài viết gồm một claim Ligue 1 và một claim Ronaldo.",
        "category": "bong-da",
        "global_entities": ["Ligue 1", "Cristiano Ronaldo"],
        "sub_claims": [
            {
                "claim": "Danh sách top ghi bàn Ligue 1 mùa 2025/2026 được công bố.",
                "entities": ["Ligue 1"],
                "time_refs": ["2025/2026"],
                "needs_web": False,
                "priority": "medium",
                "kb_evidence": [
                    {
                        "title": "Top ghi bàn vua phá lưới bóng đá Pháp Ligue 1 2025/2026",
                        "url": "https://example.com/ligue-1-scorers",
                        "domain": "example.com",
                        "content": "Danh sách cầu thủ ghi bàn Ligue 1 2025/2026.",
                        "match_source": "keyword+vector",
                    }
                ],
                "web_evidence": None,
                "verdict": None,
                "confidence": None,
                "reasoning": None,
                "evidence": None,
            },
            {
                "claim": "Cristiano Ronaldo ký hợp đồng hai năm với Al-Nassr vào ngày 25/4/2026.",
                "entities": ["Cristiano Ronaldo", "Al-Nassr"],
                "time_refs": ["25/4/2026"],
                "needs_web": True,
                "priority": "high",
                "kb_evidence": [],
                "web_evidence": [
                    {
                        "title": "Ronaldo contract status report",
                        "url": "https://example.com/ronaldo-contract",
                        "domain": "example.com",
                        "content": "No new Al-Nassr contract was signed on April 25, 2026.",
                        "score": 0.92,
                    }
                ],
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
        "llm_calls": 1,
        "tavily_calls": 0,
    }


async def main():
    fake_llm = FakeLLM()
    original_get_llm = judge_module._get_llm
    judge_module._get_llm = lambda: fake_llm

    try:
        state = build_state()
        internal_result = await judge_module.judge_internal(state)
        after_internal_claims = internal_result["sub_claims"]

        assert internal_result["llm_calls"] == 2, "judge_internal phải tăng llm_calls thêm 1"
        assert after_internal_claims[0]["verdict"] == "SUPPORTED", "Claim 0 phải SUPPORTED"
        assert after_internal_claims[0]["needs_web"] is False, "Claim 0 không cần web"
        assert after_internal_claims[0]["evidence"], "Claim 0 phải có evidence được chọn"
        assert after_internal_claims[1]["verdict"] == "NEI", "Claim 1 phải NEI sau internal judge"
        assert after_internal_claims[1]["needs_web"] is True, "Claim 1 phải được route sang web"

        state_after_internal = {**state, **internal_result}
        web_result = await judge_module.judge_after_web(state_after_internal)
        after_web_claims = web_result["sub_claims"]

        assert web_result["llm_calls"] == 3, "judge_after_web phải tăng llm_calls thêm 1"
        assert after_web_claims[0]["verdict"] == "SUPPORTED", "Claim 0 không được bị judge lại"
        assert after_web_claims[1]["verdict"] == "REFUTED", "Claim 1 phải được cập nhật từ web judge"
        assert after_web_claims[1]["needs_web"] is False, "Claim 1 không cần web sau web judge"
        assert after_web_claims[1]["confidence"] == 0.91, "Confidence claim 1 không đúng"
        assert fake_llm.calls == 2, "LLM chỉ nên được gọi 2 lần trong test này"

        fallback_claims = judge_module._apply_judgments(
            state["sub_claims"][:1],
            {
                "claims": [
                    {
                        "idx": 0,
                        "verdict": "REFUTED",
                        "confidence": 0.0,
                        "reasoning": "Bằng chứng phủ định trực tiếp claim.",
                        "needs_web": False,
                        "evidence": [
                            {
                                "title": "Nguồn phủ định",
                                "url": "https://example.com/refute",
                                "relevance": "Phủ định trực tiếp.",
                            }
                        ],
                    }
                ]
            },
            included_indices={0},
            default_needs_web=False,
        )
        assert fallback_claims[0]["confidence"] == judge_module.MIN_DECISIVE_CONFIDENCE, (
            "REFUTED/SUPPORTED có reasoning/evidence không nên giữ confidence 0.0"
        )

        speculative_claims = judge_module._apply_judgments(
            [
                {
                    "claim": "Giannis Antetokounmpo sẽ rời Milwaukee Bucks sau mùa giải 2025/2026.",
                    "entities": ["Giannis Antetokounmpo", "Milwaukee Bucks"],
                    "time_refs": ["2025/2026"],
                    "needs_web": True,
                    "priority": "high",
                    "kb_evidence": [],
                    "web_evidence": [],
                    "verdict": None,
                    "confidence": None,
                    "reasoning": None,
                    "evidence": None,
                }
            ],
            {
                "claims": [
                    {
                        "idx": 0,
                        "verdict": "SUPPORTED",
                        "confidence": 0.8,
                        "reasoning": "Bằng chứng cho thấy Giannis đang xem xét rời Bucks.",
                        "needs_web": False,
                        "evidence": [
                            {
                                "title": "Giannis could leave Bucks after this season",
                                "url": "https://example.com/giannis-rumor",
                                "relevance": "Nguồn nói đây là trade rumors.",
                            }
                        ],
                    }
                ]
            },
            included_indices={0},
            default_needs_web=False,
        )
        assert speculative_claims[0]["verdict"] == "NEI", (
            "Claim tương lai chắc chắn không được SUPPORTED nếu evidence chỉ là tin đồn/khả năng"
        )
    finally:
        judge_module._get_llm = original_get_llm

    print("=" * 60)
    print("TEST JUDGE NODES")
    print("=" * 60)
    print(json.dumps({"after_internal": internal_result, "after_web": web_result}, ensure_ascii=False, indent=2))
    print("\nTất cả assertion cho judge_internal và judge_after_web đều hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
