"""
@brief Unit test cho node synthesize.
@details Test rule tổng hợp final_verdict, confidence có trọng số và dedupe sources.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

from app.agent.nodes.synthesize import synthesize


def make_claim(
    claim: str,
    verdict: str,
    confidence: float,
    priority: str = "medium",
    url: str = "https://example.com/source",
) -> dict:
    """
    @brief Tạo claim mẫu đã có verdict/evidence để test synthesize.
    """
    return {
        "claim": claim,
        "entities": [],
        "time_refs": [],
        "needs_web": False,
        "priority": priority,
        "kb_evidence": [],
        "web_evidence": [],
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": f"Reasoning cho {claim}",
        "evidence": [
            {
                "title": f"Nguồn cho {claim}",
                "url": url,
                "relevance": "Nguồn liên quan trực tiếp.",
            }
        ],
    }


def build_state(claims: list[dict]) -> dict:
    """
    @brief Tạo AgentState tối thiểu cho node synthesize.
    """
    return {
        "messages": [],
        "user_input": "",
        "article_text": None,
        "summary": "Summary mẫu.",
        "category": "bong-da",
        "global_entities": [],
        "sub_claims": claims,
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


async def assert_case(name: str, claims: list[dict], expected_verdict: str):
    """
    @brief Chạy một case synthesize và assert final verdict.
    """
    result = await synthesize(build_state(claims))
    assert result["final_verdict"] == expected_verdict, (
        f"{name}: expected {expected_verdict}, got {result['final_verdict']}"
    )
    assert isinstance(result["confidence"], float), f"{name}: confidence phải là float"
    assert result["explanation"], f"{name}: thiếu explanation"
    assert isinstance(result["sources"], list), f"{name}: sources phải là list"
    return result


async def main():
    """
    @brief Chạy các case chính của synthesize.
    """
    all_supported = await assert_case(
        "all_supported",
        [
            make_claim("Claim A", "SUPPORTED", 0.9, "high", "https://example.com/a"),
            make_claim("Claim B", "SUPPORTED", 0.8, "medium", "https://example.com/b"),
        ],
        "SUPPORTED",
    )

    one_refuted = await assert_case(
        "one_refuted",
        [
            make_claim("Claim A", "REFUTED", 0.92, "high", "https://example.com/a"),
            make_claim("Claim B", "NEI", 0.2, "medium", "https://example.com/b"),
        ],
        "REFUTED",
    )

    mixed = await assert_case(
        "mixed",
        [
            make_claim("Claim A", "SUPPORTED", 0.88, "medium", "https://example.com/a"),
            make_claim("Claim B", "REFUTED", 0.77, "medium", "https://example.com/b"),
        ],
        "MIXED",
    )

    major_refuted_wins = await assert_case(
        "major_refuted_wins",
        [
            make_claim("Claim chính", "REFUTED", 0.82, "high", "https://example.com/a"),
            make_claim("Claim phụ", "SUPPORTED", 0.9, "medium", "https://example.com/b"),
            make_claim("Claim thiếu dữ liệu", "NEI", 0.2, "low", "https://example.com/c"),
        ],
        "REFUTED",
    )

    strong_refuted_wins = await assert_case(
        "strong_refuted_wins",
        [
            make_claim("Claim A", "SUPPORTED", 0.8, "medium", "https://example.com/a"),
            make_claim("Claim B", "REFUTED", 0.9, "medium", "https://example.com/b"),
        ],
        "REFUTED",
    )

    supported_with_nei = await assert_case(
        "supported_with_nei",
        [
            make_claim("Claim A", "SUPPORTED", 0.8, "medium", "https://example.com/a"),
            make_claim("Claim B", "NEI", 0.15, "low", "https://example.com/b"),
        ],
        "MIXED",
    )

    all_nei = await assert_case(
        "all_nei",
        [
            make_claim("Claim A", "NEI", 0.1, "medium", "https://example.com/a"),
            make_claim("Claim B", "NEI", 0.2, "medium", "https://example.com/a"),
        ],
        "NEI",
    )
    assert len(all_nei["sources"]) == 1, "Sources phải dedupe theo URL"

    print("=" * 60)
    print("TEST SYNTHESIZE NODE")
    print("=" * 60)
    print(json.dumps({
        "all_supported": all_supported,
        "one_refuted": one_refuted,
        "mixed": mixed,
        "major_refuted_wins": major_refuted_wins,
        "strong_refuted_wins": strong_refuted_wins,
        "supported_with_nei": supported_with_nei,
        "all_nei": all_nei,
    }, ensure_ascii=False, indent=2))
    print("\nTất cả assertion cho synthesize node đều hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
