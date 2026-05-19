"""
@brief Web Search Tool (Lớp 2) — Tavily Search API
@details
  Khi Internal RAG (Lớp 1) trả kết quả NEI (Not Enough Information),
  Agent sẽ kích hoạt module này để tìm kiếm thông tin mới nhất trên Internet.

  Tavily Search tối ưu cho AI Agent:
    - Trả kết quả dạng text sạch (không cần parse HTML)
    - Hỗ trợ filter theo domain, ngày, topic
    - Tốc độ nhanh, phù hợp real-time fact-checking

  API Key đọc từ .env: TAVILY_API_KEY

Usage:
    from app.agent.tools.searcher import web_search

    results = await web_search("Medvedev vô địch Monte Carlo 2026")
"""

import os
import re
from typing import Optional
from dotenv import load_dotenv
from tavily import TavilyClient, AsyncTavilyClient

load_dotenv()


# ================================================================
#  TAVILY CLIENT (khởi tạo 1 lần)
# ================================================================

_api_key = os.getenv("TAVILY_API_KEY", "")

if not _api_key:
    print("⚠️  [Searcher] TAVILY_API_KEY chưa được cấu hình trong .env!")

# Client đồng bộ (dùng cho test nhanh)
tavily_sync = TavilyClient(api_key=_api_key) if _api_key else None

# Client bất đồng bộ (dùng trong pipeline Agent)
tavily_async = AsyncTavilyClient(api_key=_api_key) if _api_key else None


# ================================================================
#  Domain và query context theo từng môn thể thao
#  Strict domains ưu tiên nguồn chuyên biệt để giảm nhiễu từ các trang quá rộng.
#  Fallback domains chỉ nên dùng thủ công khi strict search không đủ kết quả.
# ================================================================

SPORT_SEARCH_CONFIG = {
    "tennis": {
        "query_context": "tennis ATP WTA",
        "strict_domains": [
            "atptour.com",
            "wtatennis.com",
            "tennis.com",
            "tennis365.com",
            "tennismajors.com",
            "perfect-tennis.com",
            "tennishead.net",
        ],
        "fallback_domains": ["eurosport.com", "espn.com", "vnexpress.net"],
    },
    "bong-da": {
        "query_context": "football soccer bóng đá",
        "strict_domains": [
            "fcbarcelona.com",
            "atleticodemadrid.com",
            "goal.com",
            "transfermarkt.com",
            "football365.com",
            "90min.com",
            "bongda24h.vn",
            "bongdaplus.vn",
            "bongda.com.vn",
            "thethao247.vn",
            "webthethao.vn",
            "theguardian.com",
        ],
        "fallback_domains": [
            "skysports.com",
            "bbc.com",
            "espn.com",
            "marca.com",
            "as.com",
            "football-espana.net",
            "vnexpress.net",
        ],
    },
    "bong-ro": {
        "query_context": "basketball NBA bóng rổ",
        "strict_domains": [
            "nba.com",
            "hoopshype.com",
            "sportando.basketball",
            "basketnews.com",
            "basketball-reference.com",
            "realgm.com",
        ],
        "fallback_domains": [
            "espn.com",
            "cbssports.com",
            "si.com",
            "hoopsrumors.com",
            "vnexpress.net",
        ],
    },
    "bong-chay": {
        "query_context": "baseball MLB bóng chày",
        "strict_domains": [
            "mlb.com",
            "mlbtraderumors.com",
            "baseball-reference.com",
            "fangraphs.com",
            "baseballamerica.com",
        ],
        "fallback_domains": ["espn.com", "bleacherreport.com", "vnexpress.net"],
    },
}

# Backward-compatible alias for older tests/imports.
SPORT_DOMAINS = {
    category: config["strict_domains"]
    for category, config in SPORT_SEARCH_CONFIG.items()
}

STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "have", "has", "was", "were",
    "vào", "ngày", "năm", "mùa", "cho", "với", "của", "được", "trong", "một",
    "hai", "là", "đã", "sau", "khi", "tại", "theo", "đến", "trên", "dưới",
    "football", "soccer", "bóng", "đá", "tennis", "basketball", "baseball",
}

INTENT_SYNONYMS = [
    (["hợp đồng", "ký hợp đồng", "kí hợp đồng", "ký lại", "kí lại", "lương", "gia hạn"], "contract signed re-sign return salary extension deal"),
    (["chuyển nhượng", "gia nhập", "chiêu mộ", "đầu quân", "rời", "chia tay", "đổi đội"], "transfer trade leave exit future rumors"),
    (["vô địch", "thắng", "đánh bại", "chung kết"], "champion winner beat final"),
    (["thua", "game", "playoff", "vs", "trận"], "game summary box score recap final score"),
    (["chấn thương", "nghỉ thi đấu"], "injury injured sidelined"),
    (["tin đồn", "đồn đoán"], "rumor report"),
]

GAME_RESULT_TRIGGERS = {
    "thua", "thắng", "đánh bại", "game", "playoff", "vs", "trận", "score", "box score"
}

FUTURE_RUMOR_TRIGGERS = {
    "rời", "chia tay", "đổi đội", "tương lai", "sẽ rời", "trade", "leave", "leaving",
    "future", "rumor", "rumour", "demand trade", "could leave"
}

TRANSFER_CONTRACT_TRIGGERS = {
    "ký", "kí", "hợp đồng", "chính thức", "gia hạn", "signed", "signs",
    "contract", "official", "transfer", "replacement", "replace", "thay thế"
}

PREFERRED_PATH_PATTERNS = {
    "bong-ro": ["/game/", "/games/", "/box-score", "/boxscore", "/scores", "/recap"],
}

NOISY_PATH_PATTERNS = {
    "bong-ro": ["/watch/video", "/players/", "/standings", "/stats/player"],
}


def _domains_for_category(category: Optional[str], include_fallback_domains: bool = False) -> list[str] | None:
    """
    @brief Lấy domain filter theo category.
    @details Mặc định chỉ dùng strict_domains để tăng precision; fallback domains có thể bật thủ công.
    """
    if not category or category not in SPORT_SEARCH_CONFIG:
        return None

    config = SPORT_SEARCH_CONFIG[category]
    domains = list(config["strict_domains"])
    if include_fallback_domains:
        domains.extend(config["fallback_domains"])
    return domains


def _should_use_fallback_domains(query: str, category: Optional[str]) -> bool:
    """
    @brief Bật thêm domain tin tức rộng cho claim dạng tương lai/tin đồn.
    """
    lowered = query.lower()
    if category == "bong-ro" and any(trigger in lowered for trigger in FUTURE_RUMOR_TRIGGERS):
        return True
    if category == "bong-da" and any(trigger in lowered for trigger in TRANSFER_CONTRACT_TRIGGERS):
        return True
    return False


def _build_sport_query(query: str, category: Optional[str]) -> str:
    """
    @brief Thêm ngữ cảnh môn thể thao vào query để Tavily bớt trả kết quả lạc chủ đề.
    """
    additions: list[str] = []
    if not category or category not in SPORT_SEARCH_CONFIG:
        context = ""
    else:
        context = SPORT_SEARCH_CONFIG[category]["query_context"]

    lowered = query.lower()
    additions.extend(term for term in context.split() if term.lower() not in lowered)

    for triggers, synonyms in INTENT_SYNONYMS:
        if any(trigger in lowered for trigger in triggers):
            additions.extend(term for term in synonyms.split() if term.lower() not in lowered)

    if category == "bong-ro" and any(trigger in lowered for trigger in GAME_RESULT_TRIGGERS):
        additions.extend(["site:nba.com/game", "official"])

    if not additions:
        return query
    return f"{query} {' '.join(dict.fromkeys(additions))}"


def _query_terms(query: str) -> set[str]:
    """
    @brief Tách các term có tín hiệu cao từ query để lọc nhiễu sau Tavily.
    """
    normalized = query.lower().replace("-", " ")
    tokens = re.findall(r"[a-zA-ZÀ-ỹ0-9]+", normalized)
    return {
        token
        for token in tokens
        if len(token) >= 4 and not token.isdigit() and token not in STOPWORDS
    }


def _local_relevance(result: dict, terms: set[str]) -> int:
    """
    @brief Tính điểm liên quan cục bộ dựa trên term/entity xuất hiện trong title/content/url.
    """
    if not terms:
        return 0

    haystack = " ".join([
        str(result.get("title", "")),
        str(result.get("content", "")),
        str(result.get("url", "")),
        str(result.get("domain", "")),
    ]).lower().replace("-", " ")

    return sum(1 for term in terms if term in haystack)


def _normalize_match_text(value: str) -> str:
    """
    @brief Chuẩn hóa text để match phrase/entity không phụ thuộc dấu gạch nối.
    """
    return str(value or "").lower().replace("-", " ")


def _entity_relevance(result: dict, required_terms: Optional[list[str]]) -> int:
    """
    @brief Chấm điểm match entity chính trong title/url trước, content sau.
    @details Ưu tiên title/url để tránh nhiễu từ sidebar hoặc related links trong content.
    """
    if not required_terms:
        return 0

    title_url = _normalize_match_text(
        " ".join([str(result.get("title", "")), str(result.get("url", ""))])
    )
    content = _normalize_match_text(str(result.get("content", "")))

    score = 0
    for term in required_terms:
        normalized = _normalize_match_text(term)
        if not normalized or len(normalized) < 3:
            continue
        if normalized in title_url:
            score += 3
        elif normalized in content:
            score += 1

    return score


def _source_quality(result: dict, category: Optional[str], original_query: str = "") -> int:
    """
    @brief Chấm điểm chất lượng URL theo loại nguồn phù hợp với claim.
    @details Với claim kết quả trận NBA, trang game/box score đáng tin hơn trang video/player profile.
    """
    url = _normalize_match_text(str(result.get("url", "")))
    title_content = _normalize_match_text(
        " ".join([str(result.get("title", "")), str(result.get("content", ""))])
    )
    query = _normalize_match_text(original_query)
    score = 0
    for pattern in PREFERRED_PATH_PATTERNS.get(category or "", []):
        if pattern in url:
            score += 4
    for pattern in NOISY_PATH_PATTERNS.get(category or "", []):
        if pattern in url:
            score -= 4

    if category == "bong-ro":
        if any(term in title_content for term in ["game recap", "defeated", "final score", "box score"]):
            score += 6
        if any(term in title_content for term in ["things to watch", "preview", "what to watch"]):
            score -= 3
        if any(trigger in query for trigger in FUTURE_RUMOR_TRIGGERS):
            future_terms = [
                "future", "trade", "leave", "leaving", "could leave", "committed",
                "commitment", "locked in", "demand trade", "remain", "staying",
            ]
            if any(term in title_content for term in future_terms):
                score += 6
            else:
                score -= 2
            if any(term in title_content for term in ["come to the bucks", "anthony davis exchange"]):
                score -= 8
    if category == "bong-da":
        if any(term in title_content for term in [
            "official", "sign", "signed", "contract", "transfer", "agreement",
            "replacement", "replace", "lewandowski", "griezmann",
            "barcelona", "atlético", "atletico",
        ]):
            score += 4
        if any(term in title_content for term in ["rumour", "rumor", "gossip"]):
            score -= 2
    return score


def _rank_and_filter_results(
    results: list[dict],
    original_query: str,
    required_terms: Optional[list[str]] = None,
    min_score: float = 0.05,
    category: Optional[str] = None,
) -> list[dict]:
    """
    @brief Loại kết quả quá nhiễu nếu có ít nhất một kết quả match term chính của query.
    @details Nếu tất cả đều không match, giữ nguyên kết quả để judge có thể kết luận NEI.
    """
    terms = _query_terms(original_query)
    ranked = []
    for result in results:
        item = dict(result)
        item["local_relevance"] = _local_relevance(item, terms)
        item["entity_relevance"] = _entity_relevance(item, required_terms)
        item["source_quality"] = _source_quality(item, category, original_query=original_query)
        ranked.append(item)

    if min_score > 0:
        ranked = [item for item in ranked if float(item.get("score", 0.0)) >= min_score]
    if not ranked:
        return []

    query_is_future_rumor = any(
        trigger in _normalize_match_text(original_query)
        for trigger in FUTURE_RUMOR_TRIGGERS
    )
    if query_is_future_rumor and any(item.get("source_quality", 0) >= 4 for item in ranked):
        ranked = [item for item in ranked if item.get("source_quality", 0) >= 0]

    strong_entity_relevant = [item for item in ranked if item["entity_relevance"] >= 3]
    if strong_entity_relevant:
        return sorted(
            strong_entity_relevant,
            key=lambda x: (
                x.get("source_quality", 0),
                x.get("entity_relevance", 0),
                x.get("local_relevance", 0),
                x.get("score", 0.0),
            ),
            reverse=True,
        )

    entity_relevant = [item for item in ranked if item["entity_relevance"] > 0]
    if entity_relevant:
        return sorted(
            entity_relevant,
            key=lambda x: (
                x.get("source_quality", 0),
                x.get("entity_relevance", 0),
                x.get("local_relevance", 0),
                x.get("score", 0.0),
            ),
            reverse=True,
        )

    relevant = [item for item in ranked if item["local_relevance"] > 0]
    final_results = relevant if relevant else ranked
    return sorted(
        final_results,
        key=lambda x: (x.get("source_quality", 0), x.get("local_relevance", 0), x.get("score", 0.0)),
        reverse=True,
    )


# ================================================================
#  CORE: Web Search function
# ================================================================

async def web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
    topic: str = "news",
    category: Optional[str] = None,
    include_domains: Optional[list[str]] = None,
    include_fallback_domains: bool = False,
    required_terms: Optional[list[str]] = None,
    min_score: float = 0.05,
    days: Optional[int] = None,
    verbose: bool = False,
) -> list[dict]:
    """
    Tìm kiếm thông tin trên Internet qua Tavily Search API.

    Args:
        query:           Câu truy vấn tìm kiếm
        max_results:     Số kết quả tối đa (default: 5)
        search_depth:    "basic" (nhanh, rẻ) hoặc "advanced" (sâu, chính xác hơn)
        topic:           "general" hoặc "news" (ưu tiên tin tức)
        category:        Môn thể thao → tự động filter domain uy tín
        include_domains: List domain cụ thể (override category filter)
        include_fallback_domains: Bật thêm domain rộng như ESPN/BBC khi cần recall cao hơn
        required_terms: Entity/term bắt buộc ưu tiên khi lọc kết quả sau Tavily
        min_score: Ngưỡng Tavily score tối thiểu; evidence quá thấp sẽ bị bỏ
        days:            Giới hạn kết quả trong N ngày gần nhất

    Returns:
        list[dict] — mỗi dict chứa:
            - title:   Tiêu đề bài viết
            - url:     Link gốc
            - content: Nội dung tóm tắt (text sạch từ Tavily)
            - score:   Điểm relevance (0.0 - 1.0)
            - domain:  Tên miền nguồn
    """
    def log(message: str = "") -> None:
        if verbose:
            print(message)

    log("\n" + "=" * 60)
    log("🌐 WEB SEARCH (Tavily API — Lớp 2)")
    log("=" * 60)
    search_query = _build_sport_query(query, category)
    log(f"   Query: {query}")
    if search_query != query:
        log(f"   Query mở rộng theo môn: {search_query}")

    if not tavily_async:
        log("   ❌ Tavily chưa được cấu hình! Kiểm tra TAVILY_API_KEY trong .env")
        return []

    # Xác định domain filter
    domains = include_domains
    if not domains:
        auto_fallback = _should_use_fallback_domains(query, category)
        domains = _domains_for_category(
            category,
            include_fallback_domains=include_fallback_domains or auto_fallback,
        )
        if domains:
            mode = "strict+fallback" if include_fallback_domains or auto_fallback else "strict"
            log(f"   🏷️  Filter theo category '{category}' ({mode}): {len(domains)} domains")

    async def run_tavily(search_text: str) -> list[dict]:
        search_params = {
            "query": search_text,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
            "include_answer": False,
        }

        if domains:
            search_params["include_domains"] = domains
        if days:
            search_params["days"] = days

        response = await tavily_async.search(**search_params)
        raw_results = response.get("results", [])

        articles = []
        for r in raw_results:
            url = r.get("url", "")
            domain = ""
            if url:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")

            articles.append({
                "title": r.get("title", ""),
                "url": url,
                "content": r.get("content", ""),
                "score": round(r.get("score", 0.0), 4),
                "domain": domain,
            })
        return articles

    log(f"   🔍 Depth: {search_depth} | Topic: {topic} | Max: {max_results}")

    try:
        articles = await run_tavily(search_query)
        articles = _rank_and_filter_results(
            articles,
            original_query=query,
            required_terms=required_terms,
            min_score=min_score,
            category=category,
        )

        if not articles and category == "bong-da" and required_terms:
            fallback_terms = " ".join(required_terms)
            fallback_query = f"{fallback_terms} current club transfer contract 2026 official"
            log(f"   Fallback query: {fallback_query}")
            articles = _rank_and_filter_results(
                await run_tavily(fallback_query),
                original_query=fallback_query,
                required_terms=required_terms,
                min_score=min_score,
                category=category,
            )

        # Log kết quả
        log(f"\n   ✅ Tìm được {len(articles)} bài báo:")
        for i, a in enumerate(articles, 1):
            log(f"      [{i}] {a['title'][:70]}{'...' if len(a['title']) > 70 else ''}")
            log(f"          {a['url']}")
            log(
                f"          Score: {a['score']} | "
                f"Entity: {a.get('entity_relevance', 0)} | "
                f"Local: {a.get('local_relevance', 0)} | "
                f"Quality: {a.get('source_quality', 0)} | "
                f"Nguồn: {a['domain']}"
            )

        return articles

    except Exception as e:
        log(f"   ❌ Lỗi Tavily ({type(e).__name__}): {str(e)[:200]}")
        return []


async def web_search_multi(
    queries: list[str],
    max_results_per_query: int = 3,
    search_depth: str = "advanced",
    topic: str = "news",
    category: Optional[str] = None,
    days: Optional[int] = None,
) -> list[dict]:
    """
    Tìm kiếm nhiều query cùng lúc, gộp kết quả và loại trùng.

    Dùng khi Node 1 (expand_query) trả về nhiều sub_queries,
    cho phép tìm kiếm đa chiều trên web.

    Args:
        queries:                Danh sách câu truy vấn
        max_results_per_query:  Số kết quả tối đa mỗi query
        search_depth:           "basic" hoặc "advanced"
        topic:                  "general" hoặc "news"
        category:               Môn thể thao (filter domain)
        days:                   Giới hạn kết quả trong N ngày gần nhất

    Returns:
        list[dict] — danh sách bài báo (đã loại trùng theo URL)
    """
    print("\n" + "🌐" * 30)
    print("  WEB SEARCH MULTI — Tìm kiếm đa chiều")
    print("🌐" * 30)
    print(f"   📋 {len(queries)} queries")

    all_articles = []
    seen_urls = set()

    for i, q in enumerate(queries, 1):
        print(f"\n   --- Query {i}/{len(queries)} ---")
        results = await web_search(
            query=q,
            max_results=max_results_per_query,
            search_depth=search_depth,
            topic=topic,
            category=category,
            days=days,
        )

        for article in results:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                all_articles.append(article)

    # Sắp xếp theo score giảm dần
    all_articles.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n   📊 Tổng cộng: {len(all_articles)} bài báo (đã loại trùng)")
    return all_articles
