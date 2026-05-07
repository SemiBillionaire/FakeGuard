"""
Test Internal RAG Pipeline (Lớp 1) — 3 Node workflow
"""
import asyncio
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agent.tools.rag_retriever import run_internal_rag

async def main():
    query = input("Nhập tuyên bố cần kiểm chứng: ").strip()
    if not query:
        print("Query rỗng, thoát.")
        return
    
    start = time.time()
    result = await run_internal_rag(query, top_k=10)
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"⏱️  Tổng thời gian: {elapsed:.1f}s")
    print(f"{'='*60}")
    
    # In danh sách bài báo tìm được
    print(f"\n📰 Bài báo tìm được ({len(result['evidence'])} bài):")
    for i, ev in enumerate(result['evidence'], 1):
        src_tag = ev.get('match_source', '')
        hits = ev.get('entity_hits', 0)
        print(f"  [{i}] {ev['title'][:70]}")
        print(f"      {ev['url'][:80]}")
        print(f"      Nguồn: {ev['domain']} | Match: {src_tag} | Entity hits: {hits}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
