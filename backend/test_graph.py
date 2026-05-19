"""
@brief Unit test cho LangGraph workflow.
@details Test routing bang fake node de khong goi LLM API, Tavily API hoac database.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

from app.agent.graph import build_graph
from app.agent.nodes.synthesize import synthesize


def build_initial_state(text: str) -> dict:
    """
    @brief Tao AgentState toi thieu de invoke graph trong unit test.
    """
    return {
        "messages": [],
        "user_input": text,
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


def make_claim(verdict: str | None = None, needs_web: bool = False) -> dict:
    """
    @brief Tao sub-claim mau dung chung cho cac fake node.
    """
    return {
        "claim": "Daniil Medvedev giành chức vô địch ATP Monte Carlo 2026.",
        "entities": ["Daniil Medvedev", "ATP Monte Carlo"],
        "time_refs": ["2026"],
        "needs_web": needs_web,
        "priority": "high",
        "kb_evidence": [],
        "web_evidence": [],
        "verdict": verdict,
        "confidence": None,
        "reasoning": None,
        "evidence": [],
    }


def make_node_overrides(calls: list[str], internal_verdict: str) -> dict:
    """
    @brief Tao bo fake node de test luong LangGraph theo verdict noi bo mong muon.
    """

    async def fake_extract(state: dict) -> dict:
        calls.append("extract")
        return {
            "summary": "Tin nói Medvedev vô địch Monte Carlo 2026.",
            "category": "tennis",
            "global_entities": ["Daniil Medvedev", "ATP Monte Carlo"],
            "sub_claims": [make_claim()],
            "current_idx": 0,
        }

    async def fake_retrieve_internal(state: dict) -> dict:
        calls.append("retrieve_internal")
        claims = [dict(claim) for claim in state["sub_claims"]]
        evidence = [
            {
                "title": "ATP Monte Carlo result",
                "url": "https://www.atptour.com/example",
                "content": "Tournament result evidence.",
                "relevance": "internal evidence",
            }
        ]
        claims[0]["kb_evidence"] = evidence
        return {"sub_claims": claims, "kb_evidence": evidence}

    async def fake_judge_internal(state: dict) -> dict:
        calls.append("judge_internal")
        claims = [dict(claim) for claim in state["sub_claims"]]
        evidence = claims[0].get("kb_evidence", [])
        if internal_verdict == "SUPPORTED":
            claims[0].update({
                "verdict": "SUPPORTED",
                "confidence": 0.9,
                "reasoning": "Bằng chứng nội bộ xác nhận claim.",
                "needs_web": False,
                "evidence": evidence,
            })
        else:
            claims[0].update({
                "verdict": "NEI",
                "confidence": 0.2,
                "reasoning": "Bằng chứng nội bộ chưa đủ.",
                "needs_web": True,
                "evidence": [],
            })
        return {"sub_claims": claims, "llm_calls": state.get("llm_calls", 0) + 1}

    async def fake_search_web(state: dict) -> dict:
        calls.append("search_web")
        claims = [dict(claim) for claim in state["sub_claims"]]
        evidence = [
            {
                "title": "Official Monte Carlo 2026 result",
                "url": "https://www.atptour.com/news/monte-carlo-2026-final",
                "content": "The result contradicts the Medvedev claim.",
                "relevance": "web evidence",
            }
        ]
        claims[0]["web_evidence"] = evidence
        return {
            "sub_claims": claims,
            "web_evidence": evidence,
            "tavily_calls": state.get("tavily_calls", 0) + 1,
        }

    async def fake_judge_after_web(state: dict) -> dict:
        calls.append("judge_after_web")
        claims = [dict(claim) for claim in state["sub_claims"]]
        claims[0].update({
            "verdict": "REFUTED",
            "confidence": 0.86,
            "reasoning": "Kết quả web chính thức bác bỏ claim.",
            "needs_web": False,
            "evidence": claims[0].get("web_evidence", []),
        })
        return {"sub_claims": claims, "llm_calls": state.get("llm_calls", 0) + 1}

    return {
        "extract": fake_extract,
        "retrieve_internal": fake_retrieve_internal,
        "judge_internal": fake_judge_internal,
        "search_web": fake_search_web,
        "judge_after_web": fake_judge_after_web,
        "synthesize": synthesize,
    }


async def test_internal_supported_path():
    """
    @brief Khi judge_internal da SUPPORTED, graph phai bo qua Tavily va judge_after_web.
    """
    calls: list[str] = []
    graph = build_graph(make_node_overrides(calls, "SUPPORTED"))
    result = await graph.ainvoke(build_initial_state("Claim tennis mẫu"))

    assert result["final_verdict"] == "SUPPORTED"
    assert result["tavily_calls"] == 0
    assert calls == ["extract", "retrieve_internal", "judge_internal"]
    assert "search_web" not in calls
    assert "judge_after_web" not in calls


async def test_nei_fallback_web_path():
    """
    @brief Khi judge_internal tra NEI, graph phai goi Tavily roi judge lai bang web evidence.
    """
    calls: list[str] = []
    graph = build_graph(make_node_overrides(calls, "NEI"))
    result = await graph.ainvoke(build_initial_state("Claim tennis cần web"))

    assert result["final_verdict"] == "REFUTED"
    assert result["tavily_calls"] == 1
    assert result["llm_calls"] == 2
    assert calls == [
        "extract",
        "retrieve_internal",
        "judge_internal",
        "search_web",
        "judge_after_web",
    ]
    assert result["sources"][0]["url"] == "https://www.atptour.com/news/monte-carlo-2026-final"


async def main():
    """
    @brief Chay toan bo unit test graph.
    """
    await test_internal_supported_path()
    await test_nei_fallback_web_path()
    print("Tất cả assertion cho LangGraph workflow đều hợp lệ.")


if __name__ == "__main__":
    asyncio.run(main())
