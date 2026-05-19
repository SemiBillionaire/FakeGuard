"""
@brief Node tổng hợp kết quả fact-check cuối cùng.
@details Node này không gọi LLM. Nó dùng verdict từng claim để tạo final_verdict,
         confidence, explanation và danh sách nguồn tham chiếu.
"""

from collections import Counter
from typing import Any

from app.agent.state import AgentState, SubClaim


PRIORITY_WEIGHT = {
    "high": 1.5,
    "medium": 1.0,
    "low": 0.7,
}

MAJOR_REFUTATION_CONFIDENCE = 0.75
STRONG_REFUTATION_CONFIDENCE = 0.85


def _priority_weight(claim: SubClaim) -> float:
    """
    @brief Lấy trọng số theo priority của claim.
    """
    return PRIORITY_WEIGHT.get(str(claim.get("priority", "medium")).lower(), 1.0)


def _normalize_verdict(value: Any) -> str:
    """
    @brief Chuẩn hóa verdict về một trong các nhãn hợp lệ.
    """
    verdict = str(value or "NEI").strip().upper()
    return verdict if verdict in {"SUPPORTED", "REFUTED", "NEI"} else "NEI"


def _is_major_refutation(claim: SubClaim) -> bool:
    """
    @brief Xác định claim bị bác bỏ có đủ mạnh để phủ định toàn bài hay không.
    @details Claim high-priority bị REFUTED thường là trục chính của bài. Claim medium/low
             vẫn có thể phủ định toàn bài nếu confidence rất cao.
    """
    if _normalize_verdict(claim.get("verdict")) != "REFUTED":
        return False

    try:
        confidence = float(claim.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    priority = str(claim.get("priority", "medium")).lower()
    if priority == "high" and confidence >= MAJOR_REFUTATION_CONFIDENCE:
        return True
    return confidence >= STRONG_REFUTATION_CONFIDENCE


def _choose_final_verdict(sub_claims: list[SubClaim]) -> str:
    """
    @brief Chọn verdict cuối bằng rule dễ giải thích.
    @details REFUTED ưu tiên cao vì chỉ cần một luận điểm chính sai thì bài viết đáng nghi.
    """
    verdicts = [_normalize_verdict(claim.get("verdict")) for claim in sub_claims]
    has_supported = "SUPPORTED" in verdicts
    has_refuted = "REFUTED" in verdicts
    has_nei = "NEI" in verdicts

    if any(_is_major_refutation(claim) for claim in sub_claims):
        return "REFUTED"
    if has_refuted and has_supported:
        return "MIXED"
    if has_refuted:
        return "REFUTED"
    if has_supported and not has_nei:
        return "SUPPORTED"
    if has_supported and has_nei:
        return "MIXED"
    return "NEI"


def _weighted_confidence(sub_claims: list[SubClaim]) -> float:
    """
    @brief Tính confidence tổng bằng trung bình có trọng số priority.
    """
    weighted_sum = 0.0
    total_weight = 0.0
    for claim in sub_claims:
        confidence = claim.get("confidence")
        if confidence is None:
            continue
        weight = _priority_weight(claim)
        weighted_sum += float(confidence) * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 3)


def _claim_counts(sub_claims: list[SubClaim]) -> Counter:
    """
    @brief Đếm số claim theo verdict.
    """
    return Counter(_normalize_verdict(claim.get("verdict")) for claim in sub_claims)


def _dedupe_sources(sub_claims: list[SubClaim]) -> list[dict]:
    """
    @brief Gom và loại trùng sources từ evidence đã được judge chọn.
    @details Ưu tiên evidence do LLM judge chọn; nếu claim chưa có evidence được chọn,
             fallback sang web_evidence/kb_evidence để frontend vẫn có nguồn tham chiếu.
    """
    sources: list[dict] = []
    seen: set[str] = set()

    for claim in sub_claims:
        claim_text = claim.get("claim", "")
        selected_evidence = claim.get("evidence") or []
        fallback_evidence = selected_evidence
        if not fallback_evidence:
            fallback_evidence = (claim.get("web_evidence") or [])[:2] or (claim.get("kb_evidence") or [])[:2]

        for source in fallback_evidence:
            url = str(source.get("url", "")).strip()
            title = str(source.get("title", "")).strip()
            key = url or title
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append({
                "title": title,
                "url": url,
                "relevance": str(source.get("relevance", "")).strip(),
                "claim": claim_text,
                "verdict": _normalize_verdict(claim.get("verdict")),
            })

    return sources


def _build_explanation(final_verdict: str, sub_claims: list[SubClaim]) -> str:
    """
    @brief Tạo giải thích tổng hợp ngắn gọn cho người dùng.
    """
    counts = _claim_counts(sub_claims)
    parts = [
        f"Hệ thống đã kiểm chứng {len(sub_claims)} luận điểm:",
        f"{counts.get('SUPPORTED', 0)} được xác nhận,",
        f"{counts.get('REFUTED', 0)} bị bác bỏ,",
        f"{counts.get('NEI', 0)} chưa đủ thông tin.",
    ]

    if final_verdict == "SUPPORTED":
        conclusion = "Kết luận chung: nội dung được hỗ trợ bởi các bằng chứng đã thu thập."
    elif final_verdict == "REFUTED":
        conclusion = "Kết luận chung: nội dung bị bác bỏ vì có ít nhất một luận điểm trọng tâm sai hoặc mâu thuẫn rõ với bằng chứng."
    elif final_verdict == "MIXED":
        conclusion = "Kết luận chung: nội dung lẫn lộn, có luận điểm được hỗ trợ nhưng cũng có luận điểm sai hoặc chưa đủ bằng chứng."
    else:
        conclusion = "Kết luận chung: chưa đủ bằng chứng đáng tin cậy để xác nhận hoặc bác bỏ nội dung."

    reason_lines = [
        f"- {idx}. {claim.get('claim')} -> {_normalize_verdict(claim.get('verdict'))}: {claim.get('reasoning') or 'Không có giải thích chi tiết.'}"
        for idx, claim in enumerate(sub_claims, 1)
    ]

    return " ".join(parts) + " " + conclusion + "\n" + "\n".join(reason_lines)


async def synthesize(state: AgentState) -> dict:
    """
    @brief LangGraph node tổng hợp verdict cuối cùng từ các claim đã judge.
    @param state AgentState sau judge_internal hoặc judge_after_web.
    @return Dict cập nhật final_verdict, confidence, explanation và sources.
    """
    sub_claims = state.get("sub_claims", [])
    if not sub_claims:
        raise ValueError("Không có sub_claims để synthesize xử lý")

    final_verdict = _choose_final_verdict(sub_claims)
    return {
        "final_verdict": final_verdict,
        "confidence": _weighted_confidence(sub_claims),
        "explanation": _build_explanation(final_verdict, sub_claims),
        "sources": _dedupe_sources(sub_claims),
    }
