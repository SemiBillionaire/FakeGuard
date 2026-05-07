"""
Test nhanh Web Search (Lớp 2) — Tavily API
Chạy: python -X utf8 test_searcher.py
"""
import asyncio
import time
from app.agent.tools.searcher import web_search, web_search_multi


async def test_single_search():
    """Test tìm kiếm 1 query đơn."""
    print("\n" + "🧪" * 30)
    print("  TEST 1: Single Web Search")
    print("🧪" * 30)

    query = "Cristiano Ronaldo signed a two‑year contract with Al-Nassr on 25 April 2026 that includes a salary of €200 million per year."

    start = time.time()
    results = await web_search(query, max_results=5, category="bong-da")
    elapsed = time.time() - start

    print(f"\n⏱️  Thời gian: {elapsed:.1f}s")
    print(f"📰 Kết quả: {len(results)} bài báo")

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] {r['title']}")
        print(f"      URL: {r['url']}")
        print(f"      Score: {r['score']} | Domain: {r['domain']}")
        print(f"      Content: {r['content'][:150]}...")

    return results


async def test_multi_search():
    """Test tìm kiếm nhiều queries (mô phỏng output Node 1)."""
    print("\n" + "🧪" * 30)
    print("  TEST 2: Multi Web Search (đa chiều)")
    print("🧪" * 30)

    queries = [
        "Alcaraz vs Sinner chung kết Roland Garros 2026",
        "Alcaraz Sinner Roland Garros 2026 final",
        "French Open 2026 men's final results",
    ]

    start = time.time()
    results = await web_search_multi(
        queries=queries,
        max_results_per_query=3,
        category="tennis",
    )
    elapsed = time.time() - start

    print(f"\n⏱️  Tổng thời gian: {elapsed:.1f}s")
    print(f"📰 Tổng bài (đã dedup): {len(results)}")

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] {r['title']}")
        print(f"      URL: {r['url']}")
        print(f"      Score: {r['score']} | Domain: {r['domain']}")

    return results


async def test_no_filter():
    """Test tìm kiếm không filter domain — general search."""
    print("\n" + "🧪" * 30)
    print("  TEST 3: General Search (không filter domain)")
    print("🧪" * 30)

    query = "NBA playoffs 2026 results"

    start = time.time()
    results = await web_search(query, max_results=5, topic="news")
    elapsed = time.time() - start

    print(f"\n⏱️  Thời gian: {elapsed:.1f}s")
    print(f"📰 Kết quả: {len(results)} bài báo")

    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['title']} — {r['domain']}")

    return results


async def main():
    print("=" * 60)
    print("  🌐 TEST WEB SEARCH TOOL (Tavily API)")
    print("=" * 60)

    # Test 1: Single search
    r1 = await test_single_search()

    # Test 2: Multi search
    #r2 = await test_multi_search()

    # Test 3: No filter
    #r3 = await test_no_filter()

    # Summary
    print("\n" + "=" * 60)
    print("  📊 TỔNG KẾT")
    print("=" * 60)
    print(f"   Test 1 (Single):  {len(r1)} bài")
    #print(f"   Test 2 (Multi):   {len(r2)} bài")
    #print(f"   Test 3 (General): {len(r3)} bài")
    print("   ✅ Tất cả test hoàn thành!")


if __name__ == "__main__":
    asyncio.run(main())
