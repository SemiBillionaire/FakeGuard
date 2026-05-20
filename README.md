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
5. **API Fact-check Hoàn Chỉnh:** FastAPI endpoint nhận một đoạn văn đầu vào, chạy LangGraph pipeline và trả về `verdict`, `confidence`, `claims`, `sources`.

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
│   │   │   │   └── prompts.py            # Tập trung prompt cho extract/judge/synthesize
│   │   │   ├── nodes/
│   │   │   │   ├── extract.py            # Tóm tắt + tách sub-claims + category/entity
│   │   │   │   ├── retrieve_internal.py  # Truy xuất evidence nội bộ từ PostgreSQL + pgvector
│   │   │   │   ├── judge.py              # judge_internal + judge_after_web
│   │   │   │   ├── search_web.py         # Gọi Tavily cho các claim còn NEI
│   │   │   │   └── synthesize.py         # Tổng hợp verdict cuối
│   │   │   ├── tools/
│   │   │   │   └── searcher.py           # Xếp hạng và lọc kết quả Tavily theo category/claim
│   │   │   ├── config.py                 # Cấu hình LLM/Tavily cho agent
│   │   │   ├── graph.py                  # LangGraph workflow fact-check
│   │   │   ├── state.py                  # AgentState truyền giữa các bước
│   │   │   └── README.md                 # Tài liệu riêng cho agent workflow
│   │   ├── api/
│   │   │   └── chat.py                   # Endpoint /api/chat và /api/chat/stream
│   │   ├── services/
│   │   │   ├── crawler.py                # Crawl bài báo từ URL
│   │   │   └── embedding.py              # SentenceTransformer embedding service
│   │   ├── config.py                     # Cấu hình ứng dụng
│   │   ├── db.py                         # Kết nối SQLAlchemy + pgvector
│   │   └── main.py                       # Entry point FastAPI
│   ├── scripts/
│   │   ├── crawl_real_data.py            # Thu thập & deduplicate bài báo tự động
│   │   └── seed_kb.py                    # Chunk, embed và nạp dữ liệu vào DB
│   ├── test_chat.py                      # Unit test FastAPI chat endpoint
│   ├── test_extract.py                   # Unit test node extract
│   ├── test_extract_with_llm.py          # Test extract với Groq thật
│   ├── test_graph.py                     # Unit test routing của LangGraph
│   ├── test_graph_with_real_services.py  # Prototype CLI chạy graph thật
│   ├── test_judge.py                     # Unit test judge_internal / judge_after_web
│   ├── test_judge_with_rag.py            # Test judge với RAG + LLM thật
│   ├── test_rag.py                       # Test retrieve_internal với database thật
│   ├── test_search_web.py                # Unit test node search_web
│   ├── test_search_web_tavily.py         # Test Tavily thật
│   ├── test_synthesize.py                # Unit test node synthesize
│   ├── .env                              # Biến môi trường cục bộ
│   ├── .env.example                      # Mẫu biến môi trường
│   └── requirements.txt
├── Data/
│   ├── Data.md                           # Tài liệu & thống kê dữ liệu
│   ├── real_news.csv                     # Dữ liệu crawl gốc (~10,885 bài)
│   ├── real_news_prepared.csv            # Dữ liệu đã chuẩn bị (có cột ID)
│   ├── fake.csv                          # Dữ liệu tin giả (tham khảo)
│   └── pg_vector_data/                   # Volume PostgreSQL (Docker)
├── frontend/
│   └── README.md                         # Ghi chú cho phần giao diện đang phát triển
├── docker-compose.yml                    # Docker: PostgreSQL + pgvector
├── huong_dan_trien_khai_v2.md            # Hướng dẫn triển khai chi tiết
└── README.md
```

---

## ✅ 4. Các Công Việc Đã Hoàn Thành

Đến hiện tại, pipeline kiểm chứng cốt lõi đã được ghép thành prototype chạy được:

1. **Thu Thập & Xử Lý Dữ Liệu:**
   - Crawler tự động bóc tách tin tức từ các chuyên trang thể thao uy tín (`perfect-tennis.com`, `webthethao.vn`, `sportando.basketball`, `mlbtraderumors.com`).
   - Deduplication theo URL, bổ sung cột UUID cho mỗi bài.
2. **Nạp Dữ Liệu Vào Docker (VectorDB):**
   - Đã seed thành công gần **11,000 bài báo thể thao** (Bóng đá, Bóng rổ, Bóng chày, Tennis) vào PostgreSQL + pgvector chạy trên Docker.
   - Chunk size 800, overlap 100. Mỗi chunk lưu kèm metadata: `url`, `category`, `domain`, `title`, `publish_date`.
3. **LangGraph Workflow mới đã hoàn thành:**
   - `extract` -> `retrieve_internal` -> `judge_internal` -> `search_web` (nếu cần) -> `judge_after_web` -> `synthesize`.
   - Có router tự động rẽ nhánh sang Tavily khi claim còn `NEI`.
4. **Các node chính đã hoàn thành và đã tinh chỉnh:**
   - `extract.py`: tóm tắt, tách sub-claims, gán `priority`, chuẩn hóa một số entity phổ biến.
   - `retrieve_internal.py`: hybrid retrieval từ database nội bộ.
   - `judge.py`: judge nội bộ, judge lại sau web, xử lý tốt hơn với claim tương lai/tin đồn.
   - `search_web.py` + `tools/searcher.py`: Tavily search có domain filter, ranking theo category và loại claim.
   - `synthesize.py`: tổng hợp verdict cuối theo rule dễ giải thích.
5. **FastAPI chat endpoint đã hoạt động:**
   - `POST /api/chat`: trả JSON verdict hoàn chỉnh.
   - `POST /api/chat/stream`: trả SSE đơn giản một kết quả hoàn chỉnh.
6. **Đã thử nghiệm bằng claim thật:**
   - Claim `SUPPORTED/REAL`, `REFUTED/FAKE`, `NEI` đều đã được chạy qua prototype để sửa dần node.

---

## 🚀 5. Các Bước Tiếp Theo (Next Steps)

Phần graph và chat API đã xong ở mức backend prototype. Các bước tiếp theo nên là:

- [x] **Hoàn thiện `graph.py`:** Workflow LangGraph mới đã chạy được.
- [x] **Xây dựng `chat.py`:** Endpoint API đã gọi được graph thật.
- [ ] **Chuẩn hóa response và error handling cho frontend:** Gắn format ổn định hơn cho UI.
- [ ] **Phát triển frontend:** Tạo form nhập text, gọi `/api/chat`, hiển thị verdict, confidence, claims, sources.
- [ ] **Tiếp tục tinh chỉnh node:** Cải thiện retrieval/judge/search cho nhiều loại claim hơn.
- [ ] **Bổ sung đánh giá hệ thống:** Tạo tập test claim chuẩn để đo precision/recall theo từng nhãn.

---

## 🧪 6. Kiểm Thử

Mở terminal, trỏ vào thư mục `backend`. Sử dụng cờ `-X utf8` để đảm bảo in đúng ký tự tiếng Việt trên Windows.

### 6.1. Test graph bằng fake nodes

```bash
cd backend
python -X utf8 test_graph.py
```

### 6.2. Chạy prototype graph thật với LLM/DB/Tavily

```bash
cd backend
python -X utf8 test_graph_with_real_services.py --stage full
```

### 6.3. Test từng node

```bash
cd backend
python -X utf8 test_extract.py
python -X utf8 test_judge.py
python -X utf8 test_synthesize.py
python -X utf8 test_search_web.py
python -X utf8 test_rag.py
```

### 6.4. Test với dịch vụ thật

```bash
cd backend
python -X utf8 test_extract_with_llm.py
python -X utf8 test_judge_with_rag.py
python -X utf8 test_search_web_tavily.py
```

### 6.5. Test Chat API

```bash
cd backend
python -X utf8 test_chat.py
uvicorn app.main:app --reload
```
