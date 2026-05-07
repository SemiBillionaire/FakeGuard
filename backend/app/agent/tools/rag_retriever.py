"""
@brief Internal RAG Pipeline (Lớp 1) — Workflow 3 Node
@details
  [User Query]
       |
  Node 1: expand_query     → Gemini mở rộng câu hỏi (1 API call duy nhất)
       |
  Node 2: retrieve_evidence → Hybrid Search (Vector + Keyword) trên pgvector DB
       |
  Node 3: judge_evidence    → LLM đọc context bài báo → Phán quyết SUPPORTED/REFUTED/NEI
       |
  [Báo cáo fact-check]

API Keys đọc từ .env:
  - GEMINI_API_KEY  (cho Node 1 expand_query)
  - GROQ_API_KEY    (cho Node 3 judge — dùng Llama qua Groq, miễn phí & nhanh)
  - DATABASE_URL    (PostgreSQL + pgvector)
"""

import os
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import KnowledgeBase, AsyncSessionLocal
from app.services.embedding import embed_batch

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agent.core.prompts import EXPAND_QUERY_PROMPT, JUDGE_PROMPT

load_dotenv()


# ================================================================
#  LLM INSTANCES (khởi tạo 1 lần, dùng chung)
# ================================================================

# Node 1: Gemini cho query expansion (1 call / query)
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    google_api_key=os.getenv("GEMINI_API_KEY")
)

# Node 3: Groq (Llama) cho fact-check reasoning (miễn phí, nhanh, không tốn Gemini quota)
try:
    from langchain_groq import ChatGroq
    groq_llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )
except ImportError:
    groq_llm = None


# ================================================================
#  NODE 1: EXPAND QUERY (1 Gemini call duy nhất)
#  Input:  query gốc từ user
#  Output: sub_queries, hyde_doc, category, key_entities
# ================================================================

class ExpandedQuery(BaseModel):
    """Output schema cho Node 1 — tất cả trong 1 lần gọi LLM"""
    sub_queries: list[str] = Field(
        description="3-5 câu truy vấn con đa chiều (Việt + Anh). "
                    "MỞ RỘNG theo: chủ thể, hành động, đối thủ, tiếng Anh chuyên ngành. "
                    "VD: 'Trae Young chuyển đến Lakers' -> "
                    "['Trae Young chuyển nhượng', 'Lakers chiêu mộ cầu thủ', "
                    "'Trae Young trade rumors', 'Hawks trade Trae Young']"
    )
    hyde_document: str = Field(
        description="Đoạn tin tức giả định 2-3 câu, viết như sự kiện ĐÃ XẢY RA"
    )
    category: Optional[str] = Field(
        default=None,
        description="Môn thể thao: 'bong-da'|'bong-ro'|'tennis'|'esport'|'bong-chay' hoặc null"
    )
    key_entities: list[str] = Field(
        description="Tất cả tên riêng + biệt danh phổ biến. "
                    "VD: ['Trae Young', 'Lakers', 'Los Angeles Lakers', 'Atlanta Hawks', 'Hawks']"
    )

_expand_prompt = PromptTemplate(
    template=EXPAND_QUERY_PROMPT,
    input_variables=["query"],
    partial_variables={
        "format_instructions": JsonOutputParser(pydantic_object=ExpandedQuery).get_format_instructions()
    }
)

_expand_chain = _expand_prompt | gemini_llm | JsonOutputParser(pydantic_object=ExpandedQuery)


async def node_expand_query(query: str) -> dict:
    """
    NODE 1: Mở rộng câu hỏi gốc (1 Gemini API call duy nhất).
    
    Returns:
        {
            "original_query": str,
            "all_queries": [query gốc + sub_queries + hyde],
            "category": str | None,
            "key_entities": list[str]
        }
    """
    print("\n" + "="*60)
    print("📌 NODE 1: EXPAND QUERY (Gemini)")
    print("="*60)
    print(f"   Query gốc: {query}")
    
    try:
        res = await _expand_chain.ainvoke({"query": query})
        
        # Gom tất cả queries: [gốc] + [sub_queries] + [hyde]
        all_queries = [query]
        for sq in res.get("sub_queries", []):
            if sq.strip() and sq.strip() != query.strip():
                all_queries.append(sq.strip())
        
        hyde = res.get("hyde_document", "")
        if hyde.strip():
            all_queries.append(hyde.strip())
        
        category = res.get("category")
        key_entities = res.get("key_entities", [])
        
        # Log
        print(f"\n   💡 {len(all_queries)} hướng tìm kiếm:")
        for i, q in enumerate(all_queries):
            tag = "GỐC" if i == 0 else ("HyDE" if i == len(all_queries)-1 and hyde.strip() else f"SUB-{i}")
            print(f"      [{tag}] {q[:80]}{'...' if len(q) > 80 else ''}")
        if category:
            print(f"   🏷️  Category: {category}")
        if key_entities:
            print(f"   🔑 Entities: {key_entities}")
        
        return {
            "original_query": query,
            "all_queries": all_queries,
            "category": category,
            "key_entities": key_entities,
        }
    
    except Exception as e:
        print(f"   ⚠️  Gemini lỗi ({type(e).__name__}), dùng query gốc.")
        print(f"       {str(e)[:100]}")
        return {
            "original_query": query,
            "all_queries": [query],
            "category": None,
            "key_entities": [],
        }


# ================================================================
#  NODE 2: RETRIEVE EVIDENCE (Hybrid: Vector + Entity Keyword)
#  Input:  output của Node 1
#  Output: danh sách bài báo liên quan (đã dedup + rerank)
# ================================================================

async def _vector_search(
    vectors: list, session: AsyncSession, limit_per_vec: int, category: str = None
) -> list[tuple]:
    """Vector search bằng cosine similarity trên pgvector."""
    results = []
    for vec in vectors:
        stmt = select(
            KnowledgeBase,
            KnowledgeBase.embedding.cosine_distance(vec).label("dist")
        )
        if category:
            stmt = stmt.where(KnowledgeBase.category == category)
        stmt = stmt.order_by("dist").limit(limit_per_vec)
        
        for doc, dist in (await session.execute(stmt)).all():
            results.append((doc, float(dist)))
    return results


async def _entity_keyword_search(
    key_entities: list[str], session: AsyncSession,
    limit: int = 30, category: str = None
) -> list[tuple]:
    """
    ILIKE phrase search trên cụm tên riêng nguyên vẹn.
    Scoring: title match = 3.0, content match = 1.0, cộng dồn.
    """
    entities = [e.strip() for e in key_entities if len(e.strip()) >= 2]
    if not entities:
        return []
    
    score_parts, where_parts = [], []
    params = {"limit": limit}
    
    for i, ent in enumerate(entities):
        p = f"e{i}"
        params[p] = f"%{ent}%"
        score_parts.append(f"(CASE WHEN title ILIKE :{p} THEN 3.0 ELSE 0 END)")
        score_parts.append(f"(CASE WHEN content ILIKE :{p} THEN 1.0 ELSE 0 END)")
        where_parts.append(f"title ILIKE :{p}")
        where_parts.append(f"content ILIKE :{p}")
    
    cat_sql = "AND category = :cat" if category else ""
    if category:
        params["cat"] = category
    
    sql = text(f"""
        SELECT id, ({' + '.join(score_parts)}) AS score
        FROM knowledge_base
        WHERE ({' OR '.join(where_parts)}) {cat_sql}
        ORDER BY score DESC LIMIT :limit
    """)
    
    try:
        rows = (await session.execute(sql, params)).all()
        if not rows:
            return []
        
        ids = [r[0] for r in rows]
        score_map = {r[0]: float(r[1]) for r in rows}
        
        docs = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(ids))
        )).scalars().all()
        
        return [(d, score_map.get(d.id, 0)) for d in docs]
    except Exception as e:
        print(f"      [Keyword] Lỗi: {e}")
        return []


def _fuse_and_rerank(
    vec_results: list[tuple], kw_results: list[tuple], key_entities: list[str]
) -> list[dict]:
    """RRF Fusion + Entity Heuristic Reranker (không gọi LLM)."""
    scores = {}
    
    # RRF vector (distance ascending = tốt)
    vec_results.sort(key=lambda x: x[1])
    for rank, (doc, _) in enumerate(vec_results):
        k = doc.url or f"id_{doc.id}"
        if k not in scores:
            scores[k] = {"doc": doc, "rrf": 0.0, "src": set(), "boost": 0}
        scores[k]["rrf"] += 0.5 / (60 + rank)
        scores[k]["src"].add("vector")
    
    # RRF keyword (score descending = tốt)
    kw_results.sort(key=lambda x: x[1], reverse=True)
    for rank, (doc, _) in enumerate(kw_results):
        k = doc.url or f"id_{doc.id}"
        if k not in scores:
            scores[k] = {"doc": doc, "rrf": 0.0, "src": set(), "boost": 0}
        scores[k]["rrf"] += 0.5 / (60 + rank)
        scores[k]["src"].add("keyword")
    
    # Boost: cả 2 kênh x2, entity trong title x1.5/entity
    ents_lower = [e.lower() for e in key_entities if len(e) >= 2]
    for info in scores.values():
        if len(info["src"]) == 2:
            info["rrf"] *= 2.0
        title_lower = (info["doc"].title or "").lower()
        hits = sum(1 for e in ents_lower if e in title_lower)
        if hits:
            info["boost"] = hits
            info["rrf"] *= (1 + 0.5 * hits)
    
    return sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)


async def node_retrieve_evidence(expanded: dict, top_k: int = 10) -> list[dict]:
    """
    NODE 2: Truy xuất VectorDB (Hybrid Search).
    
    Args:
        expanded: output của node_expand_query
        top_k: số bài báo trả về (đã dedup)
    
    Returns:
        list[dict] — mỗi dict chứa: id, title, url, domain, language, content, publish_date, match_source
    """
    print("\n" + "="*60)
    print("📌 NODE 2: RETRIEVE EVIDENCE (Hybrid Search)")
    print("="*60)
    
    all_queries = expanded["all_queries"]
    category = expanded["category"]
    key_entities = expanded["key_entities"]
    
    async with AsyncSessionLocal() as session:
        # — Vector Search —
        print(f"\n   🔮 [Vector] Embedding {len(all_queries)} queries...")
        vectors = embed_batch(all_queries)
        limit_per_vec = max(3, (top_k * 2) // len(vectors) + 1)
        
        vec_results = await _vector_search(vectors, session, limit_per_vec, category)
        print(f"      → {len(vec_results)} chunks")
        
        # — Entity Keyword Search —
        print(f"   📝 [Keyword] Tìm theo entity...")
        kw_results = await _entity_keyword_search(key_entities, session, top_k * 3, category)
        print(f"      → {len(kw_results)} chunks")
    
    # — Fusion + Rerank + Dedup —
    print(f"   ⚡ [Fusion + Rerank]")
    fused = _fuse_and_rerank(vec_results, kw_results, key_entities)
    
    evidence = []
    seen_urls, seen_titles = set(), set()
    
    for item in fused:
        doc = item["doc"]
        if doc.url and doc.url in seen_urls:
            continue
        if doc.title and doc.title in seen_titles:
            continue
        if doc.url:
            seen_urls.add(doc.url)
        if doc.title:
            seen_titles.add(doc.title)
        
        evidence.append({
            "id": doc.id,
            "title": doc.title,
            "domain": doc.domain,
            "url": doc.url or f"https://{doc.domain}",
            "language": doc.language or "vi",
            "content": doc.content,
            "publish_date": doc.publish_date,
            "match_source": "+".join(sorted(item["src"])),
            "entity_hits": item["boost"],
        })
        if len(evidence) >= top_k:
            break
    
    # Log
    h = sum(1 for e in evidence if e["match_source"] == "keyword+vector")
    v = sum(1 for e in evidence if e["match_source"] == "vector")
    k = sum(1 for e in evidence if e["match_source"] == "keyword")
    print(f"\n   ✅ {len(evidence)} bài | Hybrid:{h} Vector:{v} Keyword:{k}")
    
    return evidence


# ================================================================
#  NODE 3: JUDGE EVIDENCE (LLM đọc context → phán quyết)
#  Input:  query gốc + danh sách bài báo từ Node 2
#  Output: báo cáo fact-check {verdict, confidence, explanation, sources}
# ================================================================


async def node_judge_evidence(claim: str, evidence: list[dict]) -> dict:
    """
    NODE 3: Kiểm chứng & kết luận.
    Dùng Groq/Llama (miễn phí) để đọc context và suy luận.
    Fallback sang Gemini nếu Groq không khả dụng.
    
    Args:
        claim: tuyên bố cần kiểm chứng (= query gốc hoặc sub-claim)
        evidence: list bài báo từ Node 2
    
    Returns:
        {
            "verdict": "SUPPORTED" | "REFUTED" | "NEI",
            "confidence": float,
            "explanation": str,
            "key_sources": list[dict],
            "all_evidence": list[dict]  # toàn bộ bài báo đã tham chiếu
        }
    """
    print("\n" + "="*60)
    print("📌 NODE 3: JUDGE EVIDENCE (Fact-check)")
    print("="*60)
    
    if not evidence:
        print("   ⚠️  Không có bằng chứng → NEI")
        return {
            "verdict": "NEI",
            "confidence": 0.0,
            "explanation": "Không tìm thấy bài báo nào liên quan trong cơ sở dữ liệu.",
            "key_sources": [],
            "all_evidence": [],
        }
    
    # Format bằng chứng cho prompt (chỉ gửi title + content tóm tắt để tiết kiệm token)
    evidence_text = ""
    for i, ev in enumerate(evidence[:8], 1):  # Tối đa 8 bài để tránh quá dài
        content_preview = (ev["content"] or "")[:500]  # Cắt 500 ký tự đầu
        evidence_text += f"""
--- Bài {i} ---
Nguồn: {ev['domain']} ({ev['language']})
Tiêu đề: {ev['title']}
URL: {ev['url']}
Nội dung: {content_preview}
"""
    
    prompt = JUDGE_PROMPT.format(
        claim=claim,
        num_evidence=len(evidence[:8]),
        evidence_text=evidence_text
    )
    
    # Chọn LLM: ưu tiên Groq (miễn phí), fallback Gemini
    judge_llm = groq_llm if groq_llm else gemini_llm
    llm_name = "Groq/Llama-3.3-70B" if groq_llm else "Gemini"
    print(f"   🧠 Đang suy luận bằng {llm_name}...")
    
    try:
        response = await judge_llm.ainvoke(prompt)
        raw_text = response.content
        
        # Parse JSON từ response
        import json
        # Tìm JSON block trong response
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(raw_text[json_start:json_end])
        else:
            raise ValueError("Không tìm thấy JSON trong response")
        
        verdict = result.get("verdict", "NEI")
        confidence = float(result.get("confidence", 0.5))
        explanation = result.get("explanation", "")
        key_sources = result.get("key_sources", [])
        
        # Log kết quả
        emoji = {"SUPPORTED": "✅", "REFUTED": "❌", "NEI": "⚠️"}.get(verdict, "❓")
        print(f"\n   {emoji} Phán quyết: {verdict} (Confidence: {confidence:.0%})")
        print(f"   📝 {explanation[:120]}{'...' if len(explanation) > 120 else ''}")
        print(f"   📎 {len(key_sources)} nguồn trích dẫn")
        
        return {
            "verdict": verdict,
            "confidence": confidence,
            "explanation": explanation,
            "key_sources": key_sources,
            "all_evidence": evidence,
        }
    
    except Exception as e:
        print(f"   ⚠️  Lỗi LLM ({type(e).__name__}): {str(e)[:120]}")
        return {
            "verdict": "NEI",
            "confidence": 0.0,
            "explanation": f"Lỗi khi suy luận: {str(e)[:200]}",
            "key_sources": [],
            "all_evidence": evidence,
        }


# ================================================================
#  PIPELINE: Chạy cả 3 Node liền mạch
# ================================================================

async def run_internal_rag(query: str, top_k: int = 10) -> dict:
    """
    Chạy toàn bộ pipeline Lớp 1 (Internal RAG):
      Node 1: expand_query   → Gemini (1 call)
      Node 2: retrieve       → pgvector Hybrid Search (0 call)
      Node 3: judge          → Groq/Llama (1 call) 
    
    Tổng cộng: 2 API calls (1 Gemini + 1 Groq miễn phí)
    
    Returns:
        {
            "query": str,
            "expanded": dict,       # output Node 1
            "evidence": list[dict], # output Node 2
            "judgment": dict,       # output Node 3
        }
    """
    print("\n" + "🔥"*30)
    print("  INTERNAL RAG PIPELINE — LỚP 1")
    print("🔥"*30)
    
    # Node 1
    expanded = await node_expand_query(query)
    
    # Node 2
    evidence = await node_retrieve_evidence(expanded, top_k=top_k)
    
    # Node 3
    judgment = await node_judge_evidence(query, evidence)
    
    print("\n" + "="*60)
    print("📋 KẾT QUẢ CUỐI CÙNG")
    print("="*60)
    emoji = {"SUPPORTED": "✅", "REFUTED": "❌", "NEI": "⚠️"}.get(judgment["verdict"], "❓")
    print(f"   {emoji} {judgment['verdict']} (Confidence: {judgment['confidence']:.0%})")
    print(f"   📝 {judgment['explanation']}")
    if judgment["key_sources"]:
        print(f"   📎 Nguồn:")
        for s in judgment["key_sources"][:5]:
            print(f"      - {s.get('title', 'N/A')}: {s.get('url', 'N/A')}")
    
    return {
        "query": query,
        "expanded": expanded,
        "evidence": evidence,
        "judgment": judgment,
    }
