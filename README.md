# 🛡️ FakeGuard - Hệ Thống Agentic RAG Kiểm Chứng Tin Giả Thể Thao (Sports News)

FakeGuard là ứng dụng Web tích hợp AI hoạt động như một "Điều tra viên tự động" chuyên biệt cho lĩnh vực Thể thao. Hệ thống được xây dựng trên kiến trúc **Agentic RAG** (Hệ thống AI tự trị tích hợp RAG) sử dụng sức mạnh của **LangGraph** và **LLM (Gemini/Groq)**. Nó kết hợp với **PostgreSQL Vector Database** (để lưu trữ tin chuẩn) và API tìm kiếm thời gian thực (**Tavily**) để bóc tách, đối chiếu và đánh giá độ chính xác của các tin tức thể thao (Bóng đá, Bóng rổ, Bóng chày, Tennis).

---

## 🎯 1. Các Tính Năng Cốt Lõi

1. **Tóm Tắt & Phân Rã (Extraction):** Tự động tóm tắt tin tức người dùng nhập vào (Văn bản hoặc URL), sau đó bóc tách thành các luận điểm/khẳng định độc lập (Sub-claims) để kiểm chứng từng ý một.
2. **Kiểm Chứng 2 Lớp (RAG + Web Search):**
   - **Lớp 1 (Internal RAG - Workflow 3-Node):** Mở rộng truy vấn (Query Expansion), Tìm kiếm lai (Hybrid Search kết hợp Vector Search & Entity ILIKE Search) trên cơ sở dữ liệu nội bộ chứa hàng chục ngàn bài báo thể thao, và Phán quyết (Evidence Judging) sử dụng LLM.
   - **Lớp 2 (Web Search):** Nếu dữ liệu nội bộ không đủ thông tin (NEI), Agent tự động kích hoạt API tìm kiếm trên Internet (Tavily Search) để cập nhật thông tin mới nhất từ các nguồn thể thao uy tín.
3. **Kiểm Chứng Độc Lập:** Agent đối chiếu từng luận điểm với bằng chứng thu được và ra quyết định độc lập.
4. **Phản Hồi Tự Nhiên (Natural Response):** Trả về báo cáo Fact-check chi tiết với 3 trạng thái chuẩn hóa: 
   - ✅ **SUPPORTED** (Xác nhận sự thật)
   - ❌ **REFUTED** (Phản bác tin giả/xuyên tạc)
   - ⚠️ **NEI - Not Enough Information** (Không đủ bằng chứng kết luận). 
   
   *Mọi kết luận đều đính kèm URL tham chiếu minh bạch.*

---

## 🛠️ 2. Công Nghệ Sử Dụng

- **Agent Workflow:** LangGraph, LangChain.
- **Mô hình Ngôn ngữ (LLM):** Gemini (phân tích/mở rộng truy vấn), Groq Llama-3.3-70B (Suy luận/Reasoning).
- **Mô hình Embedding:** `paraphrase-multilingual-MiniLM-L12-v2` (tối ưu tốc độ).
- **Vector Database:** PostgreSQL 16 + pgvector extension (Chạy qua Docker).
- **Backend API:** FastAPI (Python), Uvicorn.
- **Công cụ Crawl:** BeautifulSoup4, httpx.
- **Frontend *(Sắp triển khai)*:** React.js / Vite / Tailwind CSS.

---

## 📂 3. Cấu Trúc Dự Án Hiện Tại

```text
DoAn/
├── backend/
│   ├── app/
│   │   ├── agent/                        # 🧠 Bộ não Agentic RAG (LangGraph)
│   │   │   ├── core/
│   │   │   │   └── prompts.py             # Tập trung toàn bộ System Prompts
│   │   │   ├── nodes/
│   │   │   │   └── summarize_and_extract.py  # Node tóm tắt & trích xuất Sub-claims
│   │   │   ├── tools/
│   │   │   │   ├── rag_retriever.py       # Lớp 1 — Internal RAG (3-Node Pipeline)
│   │   │   │   └── searcher.py            # Lớp 2 — Web Search (Tavily API)
│   │   │   ├── graph.py                   # Kết nối các Node thành Workflow
│   │   │   └── state.py                   # AgentState truyền giữa các bước
│   │   ├── api/
│   │   │   └── chat.py                    # API endpoint (FastAPI)
│   │   ├── services/
│   │   │   ├── crawler.py                 # Service crawl bài báo từ URL
│   │   │   └── embedding.py               # Service nhúng vector (SentenceTransformers)
│   │   ├── config.py                      # Cấu hình ứng dụng
│   │   ├── db.py                          # Kết nối SQLAlchemy + pgvector
│   │   └── main.py                        # Entry point FastAPI
│   ├── scripts/
│   │   ├── crawl_real_data.py             # Thu thập & deduplicate bài báo tự động
│   │   └── seed_kb.py                     # Chunk, Embed & nạp dữ liệu vào DB
│   ├── test_rag.py                        # Test luồng RAG Lớp 1
│   ├── test_searcher.py                   # Test Web Search Lớp 2
│   ├── test_summarize.py                  # Test tóm tắt & trích xuất
│   ├── .env                               # Biến môi trường (API keys)
│   └── requirements.txt
├── Data/
│   ├── Data.md                            # Tài liệu & thống kê dữ liệu
│   ├── real_news.csv                      # Dữ liệu crawl gốc (~10,885 bài)
│   ├── real_news_prepared.csv             # Dữ liệu đã chuẩn bị (có cột ID)
│   ├── fake.csv                           # Dữ liệu tin giả (tham khảo)
│   └── pg_vector_data/                    # Volume PostgreSQL (Docker)
├── frontend/                              # Giao diện người dùng (đang phát triển)
├── docker-compose.yml                     # Docker: PostgreSQL + pgvector
├── huong_dan_trien_khai_v2.md             # Hướng dẫn triển khai chi tiết
└── README.md
```

---

## ✅ 4. Các Công Việc Đã Hoàn Thành

Đến hiện tại, toàn bộ pipeline cốt lõi đã được xây dựng và kiểm thử thành công:

1. **Thu Thập & Xử Lý Dữ Liệu:**
   - Crawler tự động bóc tách tin tức từ các chuyên trang thể thao uy tín (`perfect-tennis.com`, `webthethao.vn`, `sportando.basketball`, `mlbtraderumors.com`).
   - Deduplication theo URL, bổ sung cột UUID cho mỗi bài.
2. **Nạp Dữ Liệu Vào Docker (VectorDB):**
   - Đã seed thành công gần **11,000 bài báo thể thao** (Bóng đá, Bóng rổ, Bóng chày, Tennis) vào PostgreSQL + pgvector chạy trên Docker.
   - Chunk size 800, overlap 100. Mỗi chunk lưu kèm metadata: `url`, `category`, `domain`, `title`, `publish_date`.
3. **Lớp 1 — Internal RAG (Workflow 3-Node):**
   - **Node 1 (Expand Query):** Gemini phân rã câu hỏi thành sub-queries, HyDE, và trích xuất entities.
   - **Node 2 (Hybrid Retrieve):** Vector Search (pgvector) + Entity ILIKE Search, kết hợp RRF Fusion & Entity Heuristic Reranker.
   - **Node 3 (Judge Evidence):** Groq (Llama-3.3-70B) kiểm chứng và đưa ra verdict.
4. **Lớp 2 — Web Search (Tavily):**
   - Hoàn thành `tools/searcher.py`: Tìm kiếm trên Internet khi Internal RAG không đủ bằng chứng (NEI).
5. **Tóm Tắt & Trích Xuất Sub-claims:**
   - Hoàn thành `nodes/summarize_and_extract.py`: Sử dụng Groq (Llama-3.3-70B) để tóm tắt bài báo và trích xuất các luận điểm cần kiểm chứng.

---

## 🚀 5. Các Bước Tiếp Theo (Next Steps)

Tất cả các công cụ (Tools) và Node riêng lẻ đã hoạt động. Các bước tiếp theo tập trung vào việc ghép nối và hoàn thiện sản phẩm:

- [ ] **Fine-tune các Node:** Tinh chỉnh prompt và logic xử lý cho từng Node (Summarize, RAG Retriever, Searcher, Verifier) để cải thiện độ chính xác.
- [ ] **Ghép các Node — Hoàn thiện `graph.py`:** Kết nối tất cả các Node lại thành một Workflow LangGraph hoàn chỉnh với Router rẽ nhánh tự động (RAG → NEI → Web Search).
- [ ] **Xây Dựng Backend API:** Tạo FastAPI endpoint nhận Request (text/URL) và stream kết quả trả về.
- [ ] **Phát Triển Giao Diện (Frontend):** Thiết kế giao diện trò chuyện UI/UX trực quan cho người dùng tương tác với hệ thống.

---

## 🧪 6. Chạy Unit Test

Mở terminal, trỏ vào thư mục `backend`. Sử dụng cờ `-X utf8` để đảm bảo in đúng ký tự tiếng Việt trên Windows.

### 6.1. Test luồng Agentic RAG (Kiểm chứng nội bộ — Lớp 1)

```bash
cd backend
python -X utf8 test_rag.py
```

### 6.2. Test công cụ Web Search (Kiểm chứng — Lớp 2)

```bash
cd backend
python -X utf8 test_searcher.py
```

### 6.3. Test Tóm tắt & Trích xuất Sub-claims

```bash
cd backend
python -X utf8 test_summarize.py
```
