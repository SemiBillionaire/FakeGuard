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
#  Danh sách domain uy tín theo từng môn thể thao
#  → Dùng cho include_domains khi cần filter chính xác
# ================================================================

SPORT_DOMAINS = {
    "tennis": [
        "vnexpress.net", "perfect-tennis.com", "tennis365.com",
        "atptour.com", "wtatennis.com", "espn.com",
        "eurosport.com", "tennishead.net",
    ],
    "bong-da": [
        "vnexpress.net", "webthethao.vn", "bongda.com.vn",
        "goal.com", "espn.com", "bbc.com/sport",
        "transfermarkt.com", "theguardian.com/football",
    ],
    "bong-ro": [
        "vnexpress.net", "sportando.basketball", "espn.com",
        "nba.com", "bleacherreport.com", "hoopshype.com",
    ],
    "bong-chay": [
        "vnexpress.net", "mlbtraderumors.com", "espn.com",
        "mlb.com", "bleacherreport.com",
    ],
}


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
    days: Optional[int] = None,
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
        days:            Giới hạn kết quả trong N ngày gần nhất

    Returns:
        list[dict] — mỗi dict chứa:
            - title:   Tiêu đề bài viết
            - url:     Link gốc
            - content: Nội dung tóm tắt (text sạch từ Tavily)
            - score:   Điểm relevance (0.0 - 1.0)
            - domain:  Tên miền nguồn
    """
    print("\n" + "=" * 60)
    print("🌐 WEB SEARCH (Tavily API — Lớp 2)")
    print("=" * 60)
    print(f"   Query: {query}")

    if not tavily_async:
        print("   ❌ Tavily chưa được cấu hình! Kiểm tra TAVILY_API_KEY trong .env")
        return []

    # Xác định domain filter
    domains = include_domains
    if not domains and category and category in SPORT_DOMAINS:
        domains = SPORT_DOMAINS[category]
        print(f"   🏷️  Filter theo category '{category}': {len(domains)} domains")

    # Build search params
    search_params = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": False,
    }

    if domains:
        search_params["include_domains"] = domains
    if days:
        search_params["days"] = days

    print(f"   🔍 Depth: {search_depth} | Topic: {topic} | Max: {max_results}")

    try:
        # Gọi Tavily API
        response = await tavily_async.search(**search_params)
        raw_results = response.get("results", [])

        # Chuẩn hóa kết quả
        articles = []
        for r in raw_results:
            url = r.get("url", "")
            # Trích xuất domain từ URL
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

        # Log kết quả
        print(f"\n   ✅ Tìm được {len(articles)} bài báo:")
        for i, a in enumerate(articles, 1):
            print(f"      [{i}] {a['title'][:70]}{'...' if len(a['title']) > 70 else ''}")
            print(f"          {a['url']}")
            print(f"          Score: {a['score']} | Nguồn: {a['domain']}")

        return articles

    except Exception as e:
        print(f"   ❌ Lỗi Tavily ({type(e).__name__}): {str(e)[:200]}")
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
