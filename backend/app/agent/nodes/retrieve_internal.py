"""
@brief Node truy xuất bằng chứng nội bộ từ PostgreSQL + pgvector.
@details Node này không gọi LLM. Nó dùng claim text để vector search và dùng
         entities để keyword search, sau đó hợp nhất kết quả bằng RRF.
"""

from typing import Any

from app.agent.state import AgentState, SubClaim


def _unique_entities(*entity_groups: list[str]) -> list[str]:
    """
    @brief Gộp nhiều danh sách entity và loại trùng nhưng vẫn giữ thứ tự xuất hiện.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for group in entity_groups:
        for entity in group or []:
            value = str(entity).strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                merged.append(value)
    return merged


async def _vector_search(
    vectors: list[list[float]],
    session: Any,
    limit_per_vec: int,
    category: str | None = None,
) -> list[tuple]:
    """
    @brief Tìm các chunk gần nhất bằng cosine distance trên cột embedding.
    """
    from sqlalchemy import select
    from app.db import KnowledgeBase

    results = []
    for vec in vectors:
        stmt = select(
            KnowledgeBase,
            KnowledgeBase.embedding.cosine_distance(vec).label("dist"),
        )
        if category and category != "unknown":
            stmt = stmt.where(KnowledgeBase.category == category)
        stmt = stmt.order_by("dist").limit(limit_per_vec)

        for doc, dist in (await session.execute(stmt)).all():
            results.append((doc, float(dist)))
    return results


async def _entity_keyword_search(
    key_entities: list[str],
    session: Any,
    limit: int = 30,
    category: str | None = None,
) -> list[tuple]:
    """
    @brief Tìm bằng chứng theo entity bằng ILIKE trên title/content.
    @details Title match được điểm cao hơn content match vì thường phản ánh trọng tâm bài.
    """
    from sqlalchemy import select, text
    from app.db import KnowledgeBase

    entities = [entity.strip() for entity in key_entities if len(entity.strip()) >= 2]
    if not entities:
        return []

    score_parts: list[str] = []
    where_parts: list[str] = []
    params: dict[str, Any] = {"limit": limit}

    for i, entity in enumerate(entities):
        param = f"e{i}"
        params[param] = f"%{entity}%"
        score_parts.append(f"(CASE WHEN title ILIKE :{param} THEN 3.0 ELSE 0 END)")
        score_parts.append(f"(CASE WHEN content ILIKE :{param} THEN 1.0 ELSE 0 END)")
        where_parts.append(f"title ILIKE :{param}")
        where_parts.append(f"content ILIKE :{param}")

    cat_sql = "AND category = :cat" if category and category != "unknown" else ""
    if cat_sql:
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

        ids = [row[0] for row in rows]
        score_map = {row[0]: float(row[1]) for row in rows}
        docs = (
            await session.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(ids)))
        ).scalars().all()
        return [(doc, score_map.get(doc.id, 0.0)) for doc in docs]
    except Exception as exc:
        print(f"      [Keyword] Lỗi: {exc}")
        return []


def _fuse_and_rerank(
    vec_results: list[tuple],
    kw_results: list[tuple],
    key_entities: list[str],
) -> list[dict]:
    """
    @brief Hợp nhất vector results và keyword results bằng RRF + boost entity trong title.
    """
    scores: dict[str, dict] = {}

    vec_results.sort(key=lambda item: item[1])
    for rank, (doc, _) in enumerate(vec_results):
        key = doc.url or f"id_{doc.id}"
        if key not in scores:
            scores[key] = {"doc": doc, "rrf": 0.0, "src": set(), "boost": 0}
        scores[key]["rrf"] += 0.5 / (60 + rank)
        scores[key]["src"].add("vector")

    kw_results.sort(key=lambda item: item[1], reverse=True)
    for rank, (doc, _) in enumerate(kw_results):
        key = doc.url or f"id_{doc.id}"
        if key not in scores:
            scores[key] = {"doc": doc, "rrf": 0.0, "src": set(), "boost": 0}
        scores[key]["rrf"] += 0.5 / (60 + rank)
        scores[key]["src"].add("keyword")

    ents_lower = [entity.lower() for entity in key_entities if len(entity) >= 2]
    for info in scores.values():
        if len(info["src"]) == 2:
            info["rrf"] *= 2.0
        title_lower = (info["doc"].title or "").lower()
        hits = sum(1 for entity in ents_lower if entity in title_lower)
        if hits:
            info["boost"] = hits
            info["rrf"] *= 1 + 0.5 * hits

    return sorted(scores.values(), key=lambda item: item["rrf"], reverse=True)


def _format_evidence(fused: list[dict], top_k: int) -> list[dict]:
    """
    @brief Chuẩn hóa documents thành danh sách evidence và loại trùng theo URL/title.
    """
    evidence: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

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
            "url": doc.url or (f"https://{doc.domain}" if doc.domain else ""),
            "language": doc.language or "vi",
            "content": doc.content,
            "publish_date": doc.publish_date,
            "match_source": "+".join(sorted(item["src"])),
            "entity_hits": item["boost"],
        })

        if len(evidence) >= top_k:
            break

    return evidence


async def _retrieve_claim_evidence(
    claim: SubClaim,
    category: str | None,
    global_entities: list[str],
    top_k: int,
) -> list[dict]:
    """
    @brief Truy xuất evidence cho một claim bằng vector search + entity keyword search.
    """
    from app.db import AsyncSessionLocal
    from app.services.embedding import embed_batch

    claim_text = claim["claim"]
    key_entities = _unique_entities(claim.get("entities", []), global_entities)

    async with AsyncSessionLocal() as session:
        vectors = embed_batch([claim_text])
        vec_results = await _vector_search(vectors, session, limit_per_vec=top_k * 2, category=category)
        kw_results = await _entity_keyword_search(
            key_entities,
            session,
            limit=top_k * 3,
            category=category,
        )

    fused = _fuse_and_rerank(vec_results, kw_results, key_entities)
    return _format_evidence(fused, top_k=top_k)


async def retrieve_internal(state: AgentState, top_k: int = 5) -> dict:
    """
    @brief LangGraph node truy xuất bằng chứng nội bộ cho toàn bộ sub_claims.
    @param state AgentState đã có sub_claims, category và global_entities từ node extract.
    @param top_k Số evidence tối đa cho mỗi claim.
    @return Dict cập nhật sub_claims với trường kb_evidence.
    """
    sub_claims = state.get("sub_claims", [])
    if not sub_claims:
        raise ValueError("Không có sub_claims để retrieve_internal xử lý")

    category = state.get("category")
    global_entities = state.get("global_entities", [])

    updated_claims: list[SubClaim] = []
    for claim in sub_claims:
        updated_claim = SubClaim(**claim)
        updated_claim["kb_evidence"] = await _retrieve_claim_evidence(
            updated_claim,
            category=category,
            global_entities=global_entities,
            top_k=top_k,
        )
        updated_claims.append(updated_claim)

    return {"sub_claims": updated_claims}
