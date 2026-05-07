# Hướng dẫn Triển khai Chatbot Agentic RAG — Phiên bản 8 tuần

> **Phạm vi**: Chatbot kiểm chứng tin giả **bài báo tiếng Việt** (text + URL). Không bao gồm image/video/OCR.

---

## 1. Kiến trúc Đơn giản

```mermaid
graph TB
    subgraph "👤 Người dùng"
        USER[Dán text / URL bài báo]
    end

    subgraph "Frontend — React + Vite"
        CHAT[Chat UI + SSE Streaming]
    end

    subgraph "Backend — FastAPI"
        API["/api/chat/stream"]
        CRAWL[URL Crawler<br/>httpx + BeautifulSoup]
    end

    subgraph "Agent — LangGraph"
        A1[1. Phân rã claim]
        A2[2. Tìm bằng chứng]
        A3[3. Kiểm chứng]
        A4[4. Tổng hợp & Trả lời]
        A1 --> A2 --> A3 -->|còn claim| A2
        A3 -->|hết claim| A4
    end

    subgraph "Nguồn bằng chứng"
        TAVILY[🌐 Tavily Search API]
        PG[(PostgreSQL + pgvector<br/>Tin đã xác minh)]
    end

    subgraph "LLM"
        GEMINI[Gemini 2.0 Flash API]
    end

    USER --> CHAT --> API
    API --> CRAWL
    API --> A1
    A2 --> TAVILY
    A2 --> PG
    A1 & A3 & A4 --> GEMINI

    style A1 fill:#f9a825,stroke:#f57f17,color:#000
    style A2 fill:#2196f3,stroke:#1565c0,color:#fff
    style A3 fill:#4caf50,stroke:#2e7d32,color:#fff
    style A4 fill:#9c27b0,stroke:#6a1b9a,color:#fff
```

> [!NOTE]
> So với phiên bản trước, kiến trúc này bỏ: Classifier node (gộp vào Decomposer), Redis cache, Auth/JWT, module OCR/Image. Chỉ giữ **4 node** cốt lõi.

---

## 2. Tech Stack (đã xác minh khả dụng 04/2026)

| Thành phần | Công nghệ | Trạng thái | Ghi chú |
|---|---|---|---|
| **Frontend** | React 18 + Vite + TypeScript | ✅ | |
| **UI** | shadcn/ui + Tailwind CSS v4 | ✅ | |
| **Backend** | FastAPI | ✅ | Python ≥ 3.10 |
| **Agent** | LangGraph 1.1.6 | ✅ [PyPI](https://pypi.org/project/langgraph/) | `pip install langgraph` |
| **LLM** | Gemini 2.0 Flash | ✅ [Google AI](https://ai.google.dev/) | Free 15 RPM, 1M tokens/ngày |
| **Embeddings** | `paraphrase-multilingual-MiniLM-L12-v2` | ✅ [HuggingFace](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) | 384 dims, chạy CPU, hỗ trợ tiếng Việt |
| **Vietnamese NLP** | `underthesea` | ✅ [GitHub](https://github.com/undertheseanlp/underthesea) | Word segmentation |
| **Vector DB** | PostgreSQL 16 + pgvector | ✅ | Hybrid search |
| **Web Search** | Tavily API | ✅ [tavily.com](https://tavily.com) | Free 1,000 credits/tháng |
| **URL Crawling** | httpx + BeautifulSoup4 | ✅ | |
| **Evaluation** | ViFactCheck | ✅ [GitHub](https://github.com/TTHHA/ViFactCheck) + [HuggingFace](https://huggingface.co/datasets/tranthaihoa/vifactcheck) | 7,232 cặp claim-evidence, AAAI 2025 |

> [!WARNING]
> **Đã loại bỏ** vì outdate hoặc không truy cập:
> - ~~PhoBERT repo gốc (`github.com/vinai/phobert`)~~ → 404. Dùng trực tiếp [vinai/phobert-base-v2 trên HuggingFace](https://huggingface.co/vinai/phobert-base-v2) (vẫn OK).
> - ~~VFND dataset~~ → ngừng cập nhật. Thay bằng **ViFactCheck** (2025, active).
> - ~~ReINTEL~~ → hạn chế truy cập ngoài challenge. Dùng **ViFactCheck** làm benchmark chính.

---

## 3. Cấu trúc Project

```
fakeguard/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Pydantic Settings (.env)
│   │   ├── api/
│   │   │   └── chat.py             # POST /api/chat/stream (SSE)
│   │   ├── agent/
│   │   │   ├── state.py            # AgentState definition
│   │   │   ├── graph.py            # LangGraph — ghép nối 4 nodes
│   │   │   └── nodes/
│   │   │       ├── decomposer.py   # Phân rã claims
│   │   │       ├── retriever.py    # Tìm bằng chứng (Tavily + pgvector)
│   │   │       ├── verifier.py     # Kiểm chứng claim vs evidence
│   │   │       └── synthesizer.py  # Tổng hợp verdict + trả lời
│   │   ├── services/
│   │   │   ├── embedding.py        # Multilingual-MiniLM embeddings
│   │   │   └── crawler.py          # Crawl URL lấy nội dung bài báo
│   │   └── db.py                   # PostgreSQL + pgvector setup
│   ├── scripts/
│   │   └── seed_kb.py              # Nạp tin tức vào knowledge base
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── ThinkingSteps.tsx   # Hiện agent đang "suy nghĩ"
│   │   │   └── VerdictCard.tsx     # Card kết quả fact-check
│   │   ├── hooks/
│   │   │   └── useChat.ts          # SSE streaming hook
│   │   └── types.ts
│   └── package.json
│
└── docker-compose.yml              # PostgreSQL + pgvector container
```

---

## 4. Triển khai Từng bước

### 4.1 Setup Môi trường

```bash
# --- Backend ---
cd backend
python3 -m venv venv && source venv/bin/activate

pip install fastapi "uvicorn[standard]" pydantic-settings
pip install langgraph langchain-core langchain-google-genai
pip install tavily-python
pip install sentence-transformers underthesea
pip install "psycopg[binary]" pgvector sqlalchemy asyncpg
pip install httpx beautifulsoup4 lxml

# --- Frontend ---
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npx shadcn@latest init
npx shadcn@latest add button input card scroll-area badge
npm install lucide-react react-markdown

# --- Database ---
# docker-compose.yml chạy PostgreSQL + pgvector
docker compose up -d
```

**`.env.example`:**
```env
GOOGLE_API_KEY=your_gemini_api_key        # https://aistudio.google.com/apikey
TAVILY_API_KEY=tvly-your_tavily_key       # https://app.tavily.com
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fakeguard
```

**`docker-compose.yml`:**
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: fakeguard
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

### 4.2 Database Schema (rút gọn)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Bảng chính: tin tức đã crawl từ báo chính thống
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    url TEXT UNIQUE,
    source TEXT,                         -- VnExpress, TuoiTre...
    embedding vector(384),              -- multilingual-MiniLM = 384d
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON articles USING hnsw (embedding vector_cosine_ops);

-- Bảng lưu lịch sử fact-check
CREATE TABLE fact_checks (
    id SERIAL PRIMARY KEY,
    user_input TEXT NOT NULL,
    sub_claims JSONB,
    final_verdict TEXT,
    confidence FLOAT,
    response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 4.3 Embedding Service + URL Crawler

```python
# backend/app/services/embedding.py
from sentence_transformers import SentenceTransformer
from underthesea import word_tokenize

# Load 1 lần khi khởi động — model nhẹ, chạy CPU OK
_model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

def embed(text: str) -> list[float]:
    """Word-segment tiếng Việt rồi tạo embedding 384d."""
    segmented = word_tokenize(text, format="text")
    vec = _model.encode(segmented, normalize_embeddings=True)
    return vec.tolist()
```

```python
# backend/app/services/crawler.py
import httpx
from bs4 import BeautifulSoup

async def crawl_url(url: str) -> dict:
    """Crawl URL bài báo, trả về title + nội dung text."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; FakeGuard/1.0)"
        })
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # Lấy title
    title = ""
    if soup.title:
        title = soup.title.string or ""

    # Bỏ noise
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()

    # Lấy nội dung chính (ưu tiên <article>, fallback <p>)
    article_el = soup.find("article") or soup.find(class_="fck_detail")
    if article_el:
        content = article_el.get_text(separator="\n", strip=True)
    else:
        paragraphs = soup.find_all("p")
        content = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)

    return {"title": title.strip(), "content": content[:5000], "url": url}
```

---

### 4.4 Agent — LangGraph (Core)

#### State

```python
# backend/app/agent/state.py
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class SubClaim(TypedDict):
    claim: str
    verdict: str | None          # SUPPORTED / REFUTED / NEI
    confidence: float | None
    reasoning: str | None        # Giải thích ngắn
    evidence: list[dict] | None  # [{source, title, snippet}]

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str              # Input gốc (text hoặc URL)
    article_text: str | None     # Nội dung bài báo (nếu input = URL)

    sub_claims: list[SubClaim]
    current_idx: int             # Claim đang xử lý

    web_evidence: list[dict]     # Kết quả Tavily
    kb_evidence: list[dict]      # Kết quả pgvector

    final_verdict: str | None
    confidence: float | None
    explanation: str | None
    sources: list[dict]
```

#### Node 1 — Decomposer (phân rã claim)

```python
# backend/app/agent/nodes/decomposer.py
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.state import AgentState

PROMPT = """\
Bạn là chuyên gia phân tích tin tức tiếng Việt.

NHIỆM VỤ: Đọc bài báo/đoạn text dưới đây và trích ra tối đa 5 KHẲNG ĐỊNH CỤ THỂ
(sub-claims) có thể kiểm chứng được bằng dữ liệu. Bỏ qua nhận xét chủ quan.

Trả về JSON: {"claims": ["claim 1", "claim 2", ...]}
Chỉ trả JSON, không giải thích."""

async def decompose(state: AgentState, llm) -> dict:
    text = state.get("article_text") or state["user_input"]
    resp = await llm.ainvoke([
        SystemMessage(content=PROMPT),
        HumanMessage(content=text[:4000])   # cắt nếu quá dài
    ])

    import json
    data = json.loads(resp.content)

    sub_claims = [
        {"claim": c, "verdict": None, "confidence": None,
         "reasoning": None, "evidence": []}
        for c in data.get("claims", [])
    ]
    return {"sub_claims": sub_claims, "current_idx": 0}
```

#### Node 2 — Retriever (tìm bằng chứng)

```python
# backend/app/agent/nodes/retriever.py
from tavily import AsyncTavilyClient
from app.services.embedding import embed
from app.config import settings

tavily = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)

async def retrieve(state: AgentState, db) -> dict:
    claim = state["sub_claims"][state["current_idx"]]["claim"]

    # --- 1) Web search (Tavily) ---
    web_resp = await tavily.search(
        query=claim,
        search_depth="basic",     # 1 credit / request
        max_results=3,
        include_answer=False,
    )
    web_evidence = [
        {"source": r["url"], "title": r.get("title",""),
         "snippet": r.get("content","")[:300]}
        for r in web_resp.get("results", [])
    ]

    # --- 2) Knowledge base search (pgvector) ---
    vec = embed(claim)
    rows = await db.fetch("""
        SELECT title, content, url, 1 - (embedding <=> $1::vector) AS score
        FROM articles
        ORDER BY embedding <=> $1::vector
        LIMIT 3
    """, str(vec))

    kb_evidence = [
        {"source": r["url"], "title": r["title"],
         "snippet": r["content"][:300], "score": round(r["score"], 3)}
        for r in rows
    ]

    return {"web_evidence": web_evidence, "kb_evidence": kb_evidence}
```

#### Node 3 — Verifier (kiểm chứng)

```python
# backend/app/agent/nodes/verifier.py
from langchain_core.messages import SystemMessage, HumanMessage
import json

PROMPT = """\
Bạn là fact-checker chuyên nghiệp. Kiểm chứng CLAIM dựa trên EVIDENCE bên dưới.

CLAIM: {claim}

EVIDENCE:
{evidence}

Trả về JSON:
{{
  "verdict": "SUPPORTED" hoặc "REFUTED" hoặc "NEI",
  "confidence": 0.0 đến 1.0,
  "reasoning": "1-2 câu giải thích tiếng Việt"
}}

Quy tắc:
- SUPPORTED: ≥1 nguồn uy tín xác nhận rõ ràng
- REFUTED: có bằng chứng phản bác
- NEI: không đủ thông tin để kết luận
Chỉ trả JSON."""

async def verify(state: AgentState, llm) -> dict:
    idx = state["current_idx"]
    claim = state["sub_claims"][idx]["claim"]

    # Gộp evidence thành text
    all_ev = state["web_evidence"] + state["kb_evidence"]
    ev_text = "\n".join(
        f"[{i+1}] {e['title']} ({e['source']})\n{e['snippet']}"
        for i, e in enumerate(all_ev)
    )
    if not ev_text:
        ev_text = "(Không tìm thấy bằng chứng)"

    resp = await llm.ainvoke([
        SystemMessage(content=PROMPT.format(claim=claim, evidence=ev_text))
    ])
    result = json.loads(resp.content)

    # Cập nhật sub-claim
    updated = list(state["sub_claims"])
    updated[idx] = {
        **updated[idx],
        "verdict": result["verdict"],
        "confidence": result["confidence"],
        "reasoning": result["reasoning"],
        "evidence": all_ev,
    }

    return {
        "sub_claims": updated,
        "current_idx": idx + 1,    # chuyển claim tiếp
    }
```

#### Node 4 — Synthesizer (tổng hợp + trả lời)

```python
# backend/app/agent/nodes/synthesizer.py
from langchain_core.messages import SystemMessage, AIMessage
import json

PROMPT = """\
Bạn là chatbot FakeGuard — kiểm chứng tin giả tiếng Việt.
Dựa trên kết quả kiểm chứng bên dưới, hãy viết CÂU TRẢ LỜI cho người dùng.

KẾT QUẢ:
{results}

YÊU CẦU:
1. Mở đầu bằng verdict tổng: ✅ Đúng / ❌ Sai / ❓ Chưa rõ (kèm confidence %)
2. Liệt kê từng claim + verdict ngắn gọn
3. Trích dẫn nguồn (links)
4. Nếu REFUTED hoặc NEI, khuyên người dùng thận trọng

Viết tự nhiên, thân thiện, dễ hiểu."""

async def synthesize(state: AgentState, llm) -> dict:
    # Tổng hợp verdict
    verdicts = [sc["verdict"] for sc in state["sub_claims"] if sc["verdict"]]
    confs = [sc["confidence"] for sc in state["sub_claims"] if sc["confidence"]]

    if "REFUTED" in verdicts:
        final = "REFUTED"
    elif all(v == "SUPPORTED" for v in verdicts):
        final = "SUPPORTED"
    else:
        final = "NEI"

    avg_conf = sum(confs) / len(confs) if confs else 0.5

    # Collect sources (deduplicate)
    seen_urls = set()
    sources = []
    for sc in state["sub_claims"]:
        for ev in (sc.get("evidence") or []):
            url = ev.get("source", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append(ev)

    # Format results cho prompt
    results_text = ""
    for i, sc in enumerate(state["sub_claims"], 1):
        emoji = {"SUPPORTED": "✅", "REFUTED": "❌"}.get(sc["verdict"], "❓")
        results_text += (
            f"\nClaim {i}: {sc['claim']}\n"
            f"  Verdict: {emoji} {sc['verdict']} ({int((sc['confidence'] or 0)*100)}%)\n"
            f"  Lý do: {sc['reasoning']}\n"
        )

    resp = await llm.ainvoke([
        SystemMessage(content=PROMPT.format(results=results_text))
    ])

    return {
        "final_verdict": final,
        "confidence": round(avg_conf, 2),
        "explanation": resp.content,
        "sources": sources[:8],
        "messages": [AIMessage(content=resp.content)],
    }
```

#### Ghép nối Graph

```python
# backend/app/agent/graph.py
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from app.agent.state import AgentState
from app.agent.nodes import decomposer, retriever, verifier, synthesizer
from app.services.crawler import crawl_url
from app.config import settings

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.1,
)

# --- Wrapper nodes (inject dependencies) ---
async def node_preprocess(state: AgentState) -> dict:
    """Nếu input là URL → crawl lấy nội dung."""
    text = state["user_input"].strip()
    if text.startswith("http://") or text.startswith("https://"):
        article = await crawl_url(text)
        return {"article_text": f"{article['title']}\n\n{article['content']}"}
    return {"article_text": None}

async def node_decompose(state: AgentState) -> dict:
    return await decomposer.decompose(state, llm)

async def node_retrieve(state: AgentState) -> dict:
    from app.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await retriever.retrieve(state, conn)

async def node_verify(state: AgentState) -> dict:
    return await verifier.verify(state, llm)

async def node_synthesize(state: AgentState) -> dict:
    return await synthesizer.synthesize(state, llm)

# --- Routing ---
def more_claims(state: AgentState) -> str:
    if state["current_idx"] < len(state["sub_claims"]):
        return "retrieve"
    return "synthesize"

# --- Build graph ---
def build_graph():
    g = StateGraph(AgentState)

    g.add_node("preprocess", node_preprocess)
    g.add_node("decompose", node_decompose)
    g.add_node("retrieve",  node_retrieve)
    g.add_node("verify",    node_verify)
    g.add_node("synthesize", node_synthesize)

    g.add_edge(START, "preprocess")
    g.add_edge("preprocess", "decompose")
    g.add_edge("decompose",  "retrieve")
    g.add_edge("retrieve",   "verify")
    g.add_conditional_edges("verify", more_claims, {
        "retrieve":  "retrieve",
        "synthesize": "synthesize",
    })
    g.add_edge("synthesize", END)

    return g.compile()

agent = build_graph()
```

Sơ đồ luồng hoàn chỉnh:

```mermaid
graph TD
    S((START)) --> PRE[🔗 preprocess<br/>URL → crawl text]
    PRE --> DEC[📝 decompose<br/>Phân rã claims]
    DEC --> RET[🔍 retrieve<br/>Tavily + pgvector]
    RET --> VER[⚖️ verify<br/>Claim vs Evidence]
    VER -->|còn claim| RET
    VER -->|hết claim| SYN[📊 synthesize<br/>Tổng hợp + Trả lời]
    SYN --> E((END))

    style PRE fill:#78909c,stroke:#455a64,color:#fff
    style DEC fill:#f9a825,stroke:#f57f17,color:#000
    style RET fill:#2196f3,stroke:#1565c0,color:#fff
    style VER fill:#4caf50,stroke:#2e7d32,color:#fff
    style SYN fill:#9c27b0,stroke:#6a1b9a,color:#fff
```

---

### 4.5 Backend API — SSE Streaming

```python
# backend/app/api/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from app.agent.graph import agent
import json

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

STEP_LABELS = {
    "preprocess":  "🔗 Đang đọc bài báo...",
    "decompose":   "📝 Phân tích các luận điểm...",
    "retrieve":    "🔍 Tìm kiếm bằng chứng...",
    "verify":      "⚖️ Kiểm chứng thông tin...",
    "synthesize":  "📊 Tổng hợp kết quả...",
}

@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        initial = {
            "messages": [HumanMessage(content=req.message)],
            "user_input": req.message,
            "article_text": None,
            "sub_claims": [],
            "current_idx": 0,
            "web_evidence": [],
            "kb_evidence": [],
            "final_verdict": None,
            "confidence": None,
            "explanation": None,
            "sources": [],
        }

        async for event in agent.astream(initial, stream_mode="updates"):
            for node, output in event.items():
                payload = {
                    "step": node,
                    "label": STEP_LABELS.get(node, node),
                    "data": _extract(node, output),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

def _extract(node: str, out: dict) -> dict:
    """Chỉ gửi dữ liệu cần thiết cho frontend."""
    if node == "decompose":
        return {"claims": [sc["claim"] for sc in out.get("sub_claims", [])]}
    if node == "verify":
        idx = out.get("current_idx", 1) - 1
        claims = out.get("sub_claims", [])
        if 0 <= idx < len(claims):
            c = claims[idx]
            return {"claim": c["claim"], "verdict": c["verdict"],
                    "confidence": c["confidence"]}
    if node == "synthesize":
        return {
            "verdict": out.get("final_verdict"),
            "confidence": out.get("confidence"),
            "explanation": out.get("explanation"),
            "sources": out.get("sources", []),
            "claims": [
                {"claim": sc["claim"], "verdict": sc["verdict"],
                 "confidence": sc["confidence"], "reasoning": sc["reasoning"]}
                for sc in out.get("sub_claims", out.get("messages", [{}]))
            ] if "sub_claims" in out else [],
        }
    return {}
```

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router

app = FastAPI(title="FakeGuard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)
```

---

### 4.6 Frontend — Chat UI

#### SSE Hook

```typescript
// frontend/src/hooks/useChat.ts
import { useState, useCallback, useRef } from "react";

export interface ThinkingStep {
  step: string;
  label: string;
  data: Record<string, any>;
}

export interface Verdict {
  verdict: string;
  confidence: number;
  explanation: string;
  claims: { claim: string; verdict: string; confidence: number; reasoning: string }[];
  sources: { source: string; title: string; snippet: string }[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  verdict?: Verdict;
  steps?: ThinkingStep[];
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<ThinkingStep[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (text: string) => {
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: text };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setSteps([]);

    abortRef.current = new AbortController();
    const allSteps: ThinkingStep[] = [];
    let verdict: Verdict | undefined;
    let explanation = "";

    try {
      const resp = await fetch("http://localhost:8000/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: abortRef.current.signal,
      });

      const reader = resp.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });

        const lines = buf.split("\n\n");
        buf = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
          const evt = JSON.parse(line.slice(6));

          allSteps.push({ step: evt.step, label: evt.label, data: evt.data });
          setSteps([...allSteps]);

          if (evt.step === "synthesize" && evt.data) {
            verdict = evt.data as Verdict;
            explanation = evt.data.explanation || "";
          }
        }
      }

      const botMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: explanation,
        verdict,
        steps: allSteps,
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (e) {
      if ((e as Error).name !== "AbortError") console.error(e);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  return { messages, isLoading, steps, send, stop };
}
```

#### ThinkingSteps Component

```tsx
// frontend/src/components/ThinkingSteps.tsx
import type { ThinkingStep } from "../hooks/useChat";

const EMOJIS: Record<string, string> = {
  SUPPORTED: "✅", REFUTED: "❌", NEI: "❓",
};

export function ThinkingSteps({ steps, loading }: { steps: ThinkingStep[]; loading: boolean }) {
  if (!steps.length) return null;

  return (
    <div className="ml-10 my-2 p-3 rounded-xl bg-muted/40 border text-sm space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">🤖 Quá trình phân tích</p>
      {steps.map((s, i) => {
        const active = i === steps.length - 1 && loading;
        return (
          <div key={i} className="flex items-center gap-2">
            {active
              ? <span className="animate-spin text-xs">⏳</span>
              : <span className="text-xs text-green-500">✓</span>}
            <span className={active ? "font-medium" : "text-muted-foreground"}>
              {s.label}
            </span>
            {/* Hiện verdict badge nếu node = verify */}
            {s.step === "verify" && s.data?.verdict && (
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium
                ${s.data.verdict === "SUPPORTED" ? "bg-green-100 text-green-700" :
                  s.data.verdict === "REFUTED" ? "bg-red-100 text-red-700" :
                  "bg-yellow-100 text-yellow-700"}`}>
                {EMOJIS[s.data.verdict]} {s.data.verdict}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

#### VerdictCard Component

```tsx
// frontend/src/components/VerdictCard.tsx
import type { Verdict } from "../hooks/useChat";
import { ExternalLink } from "lucide-react";

const CONFIG = {
  SUPPORTED: { label: "Đúng sự thật",      emoji: "✅", border: "border-green-300 bg-green-50"  },
  REFUTED:   { label: "Sai sự thật",        emoji: "❌", border: "border-red-300 bg-red-50"      },
  NEI:       { label: "Chưa đủ thông tin",  emoji: "❓", border: "border-yellow-300 bg-yellow-50"},
};

export function VerdictCard({ v }: { v: Verdict }) {
  const cfg = CONFIG[v.verdict as keyof typeof CONFIG] || CONFIG.NEI;
  const pct = Math.round(v.confidence * 100);

  return (
    <div className={`rounded-xl border-2 p-4 my-3 space-y-3 ${cfg.border}`}>
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-bold">{cfg.emoji} {cfg.label}</h3>
        <span className="text-sm font-mono">{pct}% tin cậy</span>
      </div>

      {/* Confidence bar */}
      <div className="w-full h-2 bg-gray-200 rounded-full">
        <div className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`,
            backgroundColor: pct > 70 ? "#22c55e" : pct > 40 ? "#eab308" : "#ef4444" }} />
      </div>

      {/* Giải thích */}
      <p className="text-sm leading-relaxed">{v.explanation}</p>

      {/* Claims */}
      {v.claims?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase">Chi tiết</p>
          {v.claims.map((c, i) => (
            <div key={i} className="flex gap-2 text-sm">
              <span>{CONFIG[c.verdict as keyof typeof CONFIG]?.emoji || "❓"}</span>
              <span className="flex-1">{c.claim}</span>
            </div>
          ))}
        </div>
      )}

      {/* Sources */}
      {v.sources?.length > 0 && (
        <div className="pt-2 border-t space-y-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase">📚 Nguồn</p>
          {v.sources.slice(0, 5).map((s, i) => (
            <a key={i} href={s.source} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
              <ExternalLink className="w-3 h-3" /> {s.title || s.source}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## 5. Evaluation với ViFactCheck

### 5.1 Download Dataset

```bash
# Option A: HuggingFace
pip install datasets
python -c "
from datasets import load_dataset
ds = load_dataset('tranthaihoa/vifactcheck')
print(ds)
print(ds['test'][0])
"

# Option B: GitHub
git clone https://github.com/TTHHA/ViFactCheck.git
```

### 5.2 Script Evaluation

```python
# backend/scripts/evaluate.py
"""Đánh giá agent trên ViFactCheck test set."""
from datasets import load_dataset
from sklearn.metrics import classification_report
import asyncio, time

async def main():
    from app.agent.graph import agent
    from langchain_core.messages import HumanMessage

    ds = load_dataset("tranthaihoa/vifactcheck", split="test")

    # Map label: ViFactCheck dùng SUPPORTED / REFUTED / NEI
    y_true, y_pred, times = [], [], []

    for sample in ds.select(range(100)):  # test 100 samples trước
        claim = sample["claim"]
        label = sample["label"]

        t0 = time.time()
        result = await agent.ainvoke({
            "messages": [HumanMessage(content=claim)],
            "user_input": claim,
            "article_text": None,
            "sub_claims": [], "current_idx": 0,
            "web_evidence": [], "kb_evidence": [],
            "final_verdict": None, "confidence": None,
            "explanation": None, "sources": [],
        })
        times.append(time.time() - t0)

        y_true.append(label)
        y_pred.append(result.get("final_verdict", "NEI"))

    print(classification_report(y_true, y_pred))
    print(f"Avg latency: {sum(times)/len(times):.1f}s")

asyncio.run(main())
```

---

## 6. Lộ trình 8 tuần

```mermaid
gantt
    title FakeGuard — Lộ trình 8 tuần
    dateFormat  YYYY-MM-DD
    axisFormat  W%W

    section Sprint 1 — Foundation
    Setup project + Docker + DB           :s1a, 2026-04-14, 3d
    Embedding service + KB seeding        :s1b, after s1a, 4d
    URL Crawler                           :s1c, after s1b, 3d

    section Sprint 2 — Agent Core
    LangGraph state + decomposer node     :s2a, after s1c, 4d
    Retriever node (Tavily + pgvector)    :s2b, after s2a, 3d
    Verifier node                         :s2c, after s2b, 3d

    section Sprint 3 — API + UI
    Synthesizer node + graph assembly     :s3a, after s2c, 3d
    FastAPI SSE endpoint                  :s3b, after s3a, 2d
    React Chat UI + SSE hook              :s3c, after s3b, 5d

    section Sprint 4 — Polish + Report
    VerdictCard + ThinkingSteps UI        :s4a, after s3c, 3d
    Evaluation trên ViFactCheck           :s4b, after s4a, 4d
    Tuning prompts + fix bugs             :s4c, after s4b, 3d
    Viết báo cáo + Demo                   :s4d, after s4c, 4d
```

| Sprint | Tuần | Mục tiêu | Definition of Done |
|---|---|---|---|
| **1** | 1–2 | Nền tảng: DB, embeddings, crawler | `embed("xin chào")` trả vector 384d ✅, crawl VnExpress OK ✅ |
| **2** | 3–4 | Agent core: 4 nodes chạy end-to-end | Gọi `agent.ainvoke(...)` với 1 claim → trả verdict ✅ |
| **3** | 5–6 | API + UI: SSE streaming, giao diện chat | Mở browser → chat → thấy thinking steps + verdict card ✅ |
| **4** | 7–8 | Polish, eval, báo cáo | F1 ≥ 70% trên ViFactCheck ✅, demo video ✅ |

> [!IMPORTANT]
> **Tips cho sinh viên:**
> - Tuần 1–2 làm xong thì **commit milestone**, đừng để dồn cuối
> - Prompt engineering chiếm ~30% effort — chuẩn bị 5-10 test cases để iterate prompt
> - Gemini Free quota (15 RPM) đủ cho dev, nhưng khi eval cần thêm delay giữa requests
> - Tavily free 1,000 credits/tháng ≈ 500–1,000 searches — đủ cho 8 tuần nếu dev cẩn thận
