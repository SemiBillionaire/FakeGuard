"""
@brief Node judge cho workflow Agentic RAG.
@details Cung cấp hai bước judge: đánh giá evidence nội bộ và đánh giá lại
         các claim NEI sau khi có evidence web từ Tavily.
"""

import json
import os
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.agent.core.prompts import JUDGE_INTERNAL_PROMPT, JUDGE_WEB_PROMPT
from app.agent.state import AgentState, SubClaim


VALID_VERDICTS = {"SUPPORTED", "REFUTED", "NEI"}
MIN_DECISIVE_CONFIDENCE = 0.75

DEFINITE_FUTURE_TERMS = [
    "sẽ", "will", "rời", "leave", "leaving", "chia tay", "đổi đội", "trade",
]

SPECULATIVE_TERMS = [
    "có thể", "có khả năng", "xem xét", "cân nhắc", "tin đồn", "đồn đoán",
    "possible", "could", "may", "might", "rumor", "rumour", "consider",
    "considering", "speculation", "possible farewell", "trade rumors",
]

ENTITY_STOPWORDS = {"fc", "cf", "club", "đội", "mùa", "giải"}

TRANSFER_CONTRACT_TERMS = [
    "ky", "ki", "hop dong", "chuyen nhuong", "roi", "gia han", "thay the",
    "signed", "contract", "transfer", "replace", "replacement", "re-sign",
]

TRUSTED_REFUTATION_DOMAINS = {
    "fcbarcelona.com",
    "atleticodemadrid.com",
    "espn.com",
    "theguardian.com",
    "skysports.com",
    "cbssports.com",
    "nba.com",
    "atptour.com",
    "tennis.com",
    "tennis365.com",
    "apnews.com",
    "usopen.org",
}


def _get_llm() -> BaseChatModel:
    """
    @brief Khởi tạo LLM reasoning cho bước judge.
    @details Dùng Groq Llama mặc định vì bước này cần suy luận chặt và chi phí thấp.
    """
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=os.getenv("GROQ_JUDGE_MODEL", "llama-3.3-70b-versatile"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
        max_tokens=4096,
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    """
    @brief Parse JSON từ response của LLM.
    @details Chấp nhận response có <think>, markdown code block hoặc text dư.
    """
    think_match = re.search(r"<think>[\s\S]*?(?:</think>|$)", text)
    if think_match:
        text = text[think_match.end():].strip()

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Không thể parse JSON từ phản hồi judge: {exc}\nRaw: {text}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Judge response phải là JSON object: {data}")
    if not isinstance(data.get("claims"), list):
        raise ValueError(f"Judge response thiếu claims list: {data}")

    return data


def _clip_text(value: Any, limit: int) -> str:
    """
    @brief Cắt text dài trước khi đưa vào prompt để kiểm soát token.
    """
    text = str(value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _format_evidence_item(item: dict, idx: int) -> dict:
    """
    @brief Chuẩn hóa một evidence item thành payload ngắn cho LLM judge.
    """
    return {
        "evidence_idx": idx,
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "domain": item.get("domain", ""),
        "publish_date": item.get("publish_date", ""),
        "match_source": item.get("match_source", ""),
        "score": item.get("score", None),
        "content": _clip_text(item.get("content", ""), 700),
    }


def _build_claims_payload(
    sub_claims: list[SubClaim],
    evidence_key: str,
    only_nei: bool = False,
) -> tuple[str, set[int]]:
    """
    @brief Tạo JSON payload claim + evidence cho prompt judge.
    @return Tuple gồm payload string và tập claim index được gửi cho judge.
    """
    payload: list[dict] = []
    included_indices: set[int] = set()

    for idx, claim in enumerate(sub_claims):
        if only_nei and claim.get("verdict") != "NEI":
            continue

        evidence = claim.get(evidence_key) or []
        payload.append({
            "idx": idx,
            "claim": claim["claim"],
            "priority": claim.get("priority", "medium"),
            "entities": claim.get("entities", []),
            "time_refs": claim.get("time_refs", []),
            "evidence": [
                _format_evidence_item(item, evidence_idx)
                for evidence_idx, item in enumerate(evidence)
            ],
        })
        included_indices.add(idx)

    return json.dumps(payload, ensure_ascii=False, indent=2), included_indices


def _safe_confidence(value: Any) -> float:
    """
    @brief Ép confidence về khoảng 0.0-1.0.
    """
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _normalize_evidence(value: Any) -> list[dict]:
    """
    @brief Chuẩn hóa evidence do LLM chọn về list[dict].
    """
    if not isinstance(value, list):
        return []
    normalized: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "title": str(item.get("title", "")).strip(),
            "url": str(item.get("url", "")).strip(),
            "relevance": str(item.get("relevance", "")).strip(),
        })
    return normalized


def _is_speculative_support(claim: SubClaim, reasoning: str, evidence: list[dict]) -> bool:
    """
    @brief Phát hiện lỗi lấy tin đồn làm bằng chứng xác nhận cho claim tương lai chắc chắn.
    """
    claim_text = str(claim.get("claim", "")).lower()
    if not any(term in claim_text for term in DEFINITE_FUTURE_TERMS):
        return False

    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('relevance', '')}"
        for item in evidence
    ).lower()
    haystack = f"{reasoning} {evidence_text}".lower()
    return any(term in haystack for term in SPECULATIVE_TERMS)


def _fold_text(value: Any) -> str:
    """
    @brief Chuẩn hóa text về dạng không dấu/lower để so khớp entity.
    """
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _entity_tokens(entity: str) -> list[str]:
    """
    @brief Lấy token entity có ý nghĩa để kiểm tra evidence có phủ entity đó không.
    """
    return [
        token
        for token in re.findall(r"[a-z0-9]+", _fold_text(entity))
        if len(token) >= 4 and token not in ENTITY_STOPWORDS
    ]


def _missing_refutation_entities(claim: SubClaim, evidence: list[dict]) -> list[str]:
    """
    @brief Tìm entity chính chưa xuất hiện trong evidence được dùng để bác bỏ claim.
    """
    if len(claim.get("entities", [])) < 2 or not evidence:
        return []

    evidence_text = _fold_text(
        " ".join(
            f"{item.get('title', '')} {item.get('url', '')} {item.get('relevance', '')}"
            for item in evidence
        )
    )
    missing = []
    for entity in claim.get("entities", []):
        tokens = _entity_tokens(entity)
        if tokens and not any(token in evidence_text for token in tokens):
            missing.append(entity)
    return missing


def _claim_is_transfer_or_contract(claim: SubClaim) -> bool:
    """
    @brief Nhận diện claim chuyển nhượng/hợp đồng cần nguồn mạnh khi bác bỏ.
    """
    claim_text = _fold_text(claim.get("claim", ""))
    return any(term in claim_text for term in TRANSFER_CONTRACT_TERMS)


def _has_trusted_refutation_source(evidence: list[dict]) -> bool:
    """
    @brief Kiểm tra evidence đã chọn có nguồn đủ mạnh để refute claim chuyển nhượng không.
    """
    for item in evidence:
        domain = urlparse(str(item.get("url", ""))).netloc.lower().replace("www.", "")
        if domain in TRUSTED_REFUTATION_DOMAINS:
            return True
    return False


def _send_weak_internal_refutations_to_web(sub_claims: list[SubClaim]) -> list[SubClaim]:
    """
    @brief Nếu internal REFUTED nhưng evidence thiếu entity chính, chuyển sang NEI để Tavily tìm tiếp.
    """
    updated_claims = [SubClaim(**claim) for claim in sub_claims]
    for claim in updated_claims:
        if claim.get("verdict") != "REFUTED":
            continue
        evidence = claim.get("evidence") or []
        missing = _missing_refutation_entities(claim, evidence)
        weak_source = _claim_is_transfer_or_contract(claim) and not _has_trusted_refutation_source(evidence)
        if not missing and not weak_source:
            continue
        claim["verdict"] = "NEI"
        claim["confidence"] = min(float(claim.get("confidence") or 0.0), 0.35)
        claim["needs_web"] = True
        reason_parts = []
        if missing:
            reason_parts.append(f"chưa bao phủ entity chính: {', '.join(missing)}")
        if weak_source:
            reason_parts.append("nguồn nội bộ chưa đủ mạnh cho claim chuyển nhượng/hợp đồng")
        claim["reasoning"] = (
            f"{claim.get('reasoning') or ''} Bằng chứng nội bộ {', '.join(reason_parts)}; "
            "cần web evidence để kết luận chắc hơn."
        ).strip()
        claim["evidence"] = []
    return updated_claims


def _apply_judgments(
    sub_claims: list[SubClaim],
    judge_data: dict[str, Any],
    included_indices: set[int],
    default_needs_web: bool,
) -> list[SubClaim]:
    """
    @brief Ghi verdict/confidence/reasoning/evidence từ LLM vào đúng claim theo idx.
    """
    updated_claims = [SubClaim(**claim) for claim in sub_claims]

    for item in judge_data.get("claims", []):
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("idx"))
        except (TypeError, ValueError):
            continue
        if idx not in included_indices or idx < 0 or idx >= len(updated_claims):
            continue

        verdict = str(item.get("verdict", "NEI")).strip().upper()
        if verdict not in VALID_VERDICTS:
            verdict = "NEI"

        confidence = _safe_confidence(item.get("confidence"))
        reasoning = str(item.get("reasoning", "")).strip()
        evidence = _normalize_evidence(item.get("evidence"))
        if verdict == "SUPPORTED" and _is_speculative_support(updated_claims[idx], reasoning, evidence):
            verdict = "NEI"
            confidence = min(confidence, 0.35)
            reasoning = (
                reasoning
                + " Tuy nhiên bằng chứng chỉ thể hiện tin đồn/khả năng, chưa xác nhận chắc chắn sự kiện tương lai."
            ).strip()

        if verdict in {"SUPPORTED", "REFUTED"} and confidence == 0.0 and (reasoning or evidence):
            confidence = MIN_DECISIVE_CONFIDENCE

        updated_claims[idx]["verdict"] = verdict
        updated_claims[idx]["confidence"] = confidence
        updated_claims[idx]["reasoning"] = reasoning
        updated_claims[idx]["evidence"] = evidence
        updated_claims[idx]["needs_web"] = bool(item.get("needs_web", verdict == "NEI" and default_needs_web))

    return updated_claims


async def judge_internal(state: AgentState) -> dict:
    """
    @brief Judge tất cả claims dựa trên kb_evidence nội bộ.
    @details Nếu verdict là NEI, claim sẽ được đánh dấu needs_web=True để router gọi Tavily.
    """
    sub_claims = state.get("sub_claims", [])
    if not sub_claims:
        raise ValueError("Không có sub_claims để judge_internal xử lý")

    claims_payload, included_indices = _build_claims_payload(sub_claims, "kb_evidence")
    prompt = JUDGE_INTERNAL_PROMPT.format(claims_payload=claims_payload)
    response = await _get_llm().ainvoke([HumanMessage(content=prompt)])
    judge_data = _parse_json_response(response.content)

    judged_claims = _apply_judgments(
            sub_claims,
            judge_data=judge_data,
            included_indices=included_indices,
            default_needs_web=True,
        )

    return {
        "sub_claims": _send_weak_internal_refutations_to_web(judged_claims),
        "llm_calls": int(state.get("llm_calls", 0)) + 1,
    }


async def judge_after_web(state: AgentState) -> dict:
    """
    @brief Judge lại các claim còn NEI sau khi đã có web_evidence từ Tavily.
    @details Chỉ gửi claim NEI vào LLM để tiết kiệm token và không ghi đè claim đã chốt.
    """
    sub_claims = state.get("sub_claims", [])
    if not sub_claims:
        raise ValueError("Không có sub_claims để judge_after_web xử lý")

    claims_payload, included_indices = _build_claims_payload(
        sub_claims,
        evidence_key="web_evidence",
        only_nei=True,
    )
    if not included_indices:
        return {"sub_claims": sub_claims}

    prompt = JUDGE_WEB_PROMPT.format(claims_payload=claims_payload)
    response = await _get_llm().ainvoke([HumanMessage(content=prompt)])
    judge_data = _parse_json_response(response.content)

    return {
        "sub_claims": _apply_judgments(
            sub_claims,
            judge_data=judge_data,
            included_indices=included_indices,
            default_needs_web=False,
        ),
        "llm_calls": int(state.get("llm_calls", 0)) + 1,
    }
