"""
@brief Integration test cho Tavily Web Search với claim thật.
@details Test này gọi Tavily API thật để kiểm tra các bài báo trả về có liên quan
         đến claim cần fact-check hay không.

Yêu cầu:
  - backend/.env có TAVILY_API_KEY.

Chạy:
  cd backend
  python -X utf8 test_search_web_tavily.py
"""

import asyncio
import argparse
import os
import re
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))
sys.path.insert(0, BACKEND_DIR)

from app.agent.tools.searcher import web_search


DEFAULT_CLAIM = "Cristiano Ronaldo ký hợp đồng hai năm với Al-Nassr vào ngày 25/4/2026."
TERM_STOPWORDS = {
    "gianh", "giành", "chuc", "chức", "vo", "vô", "dich", "địch", "ngay", "ngày",
    "nam", "năm", "mua", "mùa", "ky", "ký", "hop", "hợp", "dong", "đồng",
    "voi", "với", "tai", "tại", "cua", "của", "cho", "tren", "trên",
}


def _strip_accents(text: str) -> str:
    """
    @brief Bỏ dấu tiếng Việt để lọc stopword ổn định hơn.
    """
    import unicodedata

    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _is_entity_token(token: str) -> bool:
    """
    @brief Nhận diện token có khả năng là entity: Title Case, ALL CAPS, số năm, hoặc chứa dấu gạch nối.
    """
    if not token:
        return False
    if token.isdigit():
        return len(token) == 4
    if "-" in token:
        return True
    if token.isupper():
        return True
    return token[0].isupper()


NORMALIZED_TERM_STOPWORDS = {_strip_accents(term.lower()) for term in TERM_STOPWORDS}


def _extract_required_terms(claim: str) -> list[str]:
    """
    @brief Suy ra vài term/entity mạnh từ claim để lọc kết quả Tavily.
    @details Ưu tiên chuỗi có chữ hoa liên tiếp và fallback sang token dài có ý nghĩa.
    """
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9-]+", claim)

    phrases: list[str] = []
    current: list[str] = []
    for token in tokens:
        if _is_entity_token(token):
            current.append(token)
        else:
            if current:
                phrases.append(" ".join(current))
                current = []
    if current:
        phrases.append(" ".join(current))

    fallback_terms = []
    for token in tokens:
        lowered = _strip_accents(token.lower())
        if len(token) < 4 or token.isdigit() or lowered in NORMALIZED_TERM_STOPWORDS:
            continue
        fallback_terms.append(token)

    merged: list[str] = []
    seen: set[str] = set()
    for term in phrases + fallback_terms:
        cleaned = term.strip(" .,!?:;")
        lowered = _strip_accents(cleaned.lower())
        if lowered not in seen:
            seen.add(lowered)
            merged.append(cleaned)

    return merged[:6]


def _contains_expected_terms(result: dict, expected_terms: list[str]) -> bool:
    """
    @brief Kiểm tra thô xem kết quả Tavily có chứa entity chính của claim không.
    @details Đây không phải judge đúng/sai, chỉ là sanity check về độ liên quan retrieval web.
    """
    haystack = " ".join([
        str(result.get("title", "")),
        str(result.get("content", "")),
        str(result.get("url", "")),
        str(result.get("domain", "")),
    ]).lower()
    return any(term.lower() in haystack for term in expected_terms)


def _parse_args() -> argparse.Namespace:
    """
    @brief Parse claim/required_terms từ command line để test nhiều case khác nhau.
    """
    parser = argparse.ArgumentParser(description="Test Tavily web search with a custom claim.")
    parser.add_argument(
        "--claim",
        default=DEFAULT_CLAIM,
        help="Claim cần test với Tavily",
    )
    parser.add_argument(
        "--required-term",
        action="append",
        dest="required_terms",
        default=None,
        help="Term/entity ưu tiên khi lọc Tavily. Có thể truyền nhiều lần.",
    )
    return parser.parse_args()


def _infer_category(claim: str) -> str:
    """
    @brief Suy luận nhanh category để test Tavily đúng domain theo môn.
    """
    lowered = claim.lower()
    if any(term in lowered for term in ["medvedev", "monte carlo", "alcaraz", "tennis", "atp", "wta"]):
        return "tennis"
    if any(term in lowered for term in [
        "lebron", "nba", "okc", "lakers", "basketball", "bóng rổ",
        "giannis", "antetokounmpo", "bucks", "milwaukee",
    ]):
        return "bong-ro"
    if any(term in lowered for term in ["mlb", "baseball", "bóng chày"]):
        return "bong-chay"
    return "bong-da"


async def main():
    """
    @brief Gọi Tavily thật và in kết quả để người dùng đánh giá độ liên quan.
    """
    args = _parse_args()
    claim = args.claim.strip()
    required_terms = args.required_terms or _extract_required_terms(claim)

    if not os.getenv("TAVILY_API_KEY"):
        raise RuntimeError("Thiếu TAVILY_API_KEY trong backend/.env")

    print("=" * 60)
    print("TEST TAVILY SEARCH WITH REAL API")
    print("=" * 60)
    print(f"Claim: {claim}")
    print(f"Required terms: {required_terms}\n")

    results = await web_search(
        query=claim,
        max_results=5,
        search_depth="basic",
        topic="news",
        category=_infer_category(claim),
        required_terms=required_terms,
        verbose=True,
    )

    assert isinstance(results, list), "Tavily phải trả về list"

    relevant_count = 0
    for idx, result in enumerate(results, 1):
        is_relevant = _contains_expected_terms(result, required_terms)
        relevant_count += int(is_relevant)

        print(f"[{idx}] {'RELATED' if is_relevant else 'UNCLEAR'} | score={result.get('score')}")
        print(f"Title: {result.get('title')}")
        print(f"URL: {result.get('url')}")
        print(f"Domain: {result.get('domain')}")
        preview = str(result.get("content") or "").replace("\n", " ")[:300]
        print(f"Content: {preview}...")
        print()

    assert relevant_count == len(results), (
        "Sau khi lọc bằng required_terms, mọi kết quả còn lại nên có dấu hiệu liên quan. "
        "Cần kiểm tra query, domain filter hoặc Tavily quota."
    )

    if results:
        print(f"Tavily trả {len(results)} kết quả, tất cả đều có dấu hiệu liên quan sau lọc.")
    else:
        print("Tavily không trả kết quả đủ mạnh sau lọc. Đây là kết quả chấp nhận được cho claim có thể sai/khó xác minh.")
    print("Lưu ý: test này chỉ kiểm tra độ liên quan sơ bộ, verdict đúng/sai vẫn do judge_after_web xử lý.")


if __name__ == "__main__":
    asyncio.run(main())
