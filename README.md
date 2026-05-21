# 🛡️ FakeGuard - Hệ Thống Agentic RAG Kiểm Chứng Tin Thể Thao

FakeGuard là ứng dụng Web kiểm chứng tin thể thao theo hướng **Agentic RAG**. Hệ thống kết hợp:

- **LangGraph** để điều phối workflow nhiều node
- **LLM (Gemini / Groq)** để extract, judge và synthesize
- **PostgreSQL + pgvector** để lưu kho bài báo nội bộ
- **Tavily** để mở rộng tìm kiếm web khi dữ liệu nội bộ chưa đủ

Mục tiêu của dự án là bóc tách một đoạn tin thành các sub-claims, truy xuất bằng chứng phù hợp, đối chiếu từng phần và trả về kết luận cuối cùng dưới dạng:

- ✅ `SUPPORTED`
- ❌ `REFUTED`
- ⚠️ `NEI`

---

## 🎯 1. Các Tính Năng Cốt Lõi

1. **Tóm tắt và tách claim**
   - Tóm tắt đoạn tin đầu vào
   - Tách thành các sub-claims để kiểm chứng độc lập
   - Gắn category và entity chính

2. **Kiểm chứng 2 lớp**
   - **Lớp 1 - Internal RAG:** truy xuất evidence từ kho dữ liệu nội bộ bằng hybrid retrieval
   - **Lớp 2 - Web Search:** nếu nội bộ chưa đủ thông tin thì gọi Tavily để lấy nguồn web mới

3. **Judge độc lập theo từng claim**
   - Judge từ evidence nội bộ
   - Nếu cần, judge lại sau khi có evidence web

4. **Tổng hợp kết luận cuối**
   - Gom kết quả từ nhiều sub-claims
   - Trả verdict cuối, độ tin cậy, giải thích và danh sách nguồn

5. **Lưu lịch sử chat**
   - Mỗi phiên chat được lưu vào PostgreSQL
   - Có thể lọc theo môn thể thao, tìm lại session cũ và xóa session

---

## 🛠️ 2. Công Nghệ Sử Dụng

- **Agent Workflow:** LangGraph, LangChain
- **LLM:** Gemini, Groq
- **Embedding:** Sentence Transformers
- **Vector Database:** PostgreSQL + pgvector
- **Web Search:** Tavily
- **Backend API:** FastAPI, Uvicorn
- **Frontend:** React, Vite
- **Local Infra:** Docker Compose

---

## 📂 3. Cấu Trúc Dự Án Hiện Tại

```text
DoAn/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── core/
│   │   │   │   └── prompts.py
│   │   │   ├── nodes/
│   │   │   │   ├── extract.py
│   │   │   │   ├── retrieve_internal.py
│   │   │   │   ├── judge.py
│   │   │   │   ├── search_web.py
│   │   │   │   └── synthesize.py
│   │   │   ├── tools/
│   │   │   │   └── searcher.py
│   │   │   ├── graph.py
│   │   │   └── state.py
│   │   ├── api/
│   │   │   └── chat.py
│   │   ├── services/
│   │   │   ├── chat_history.py
│   │   │   ├── crawler.py
│   │   │   └── embedding.py
│   │   ├── db.py
│   │   └── main.py
│   ├── scripts/
│   │   ├── crawl_real_data.py
│   │   └── seed_kb.py
│   ├── test_chat.py
│   ├── test_extract.py
│   ├── test_graph.py
│   ├── test_graph_with_real_services.py
│   ├── test_judge.py
│   ├── test_rag.py
│   ├── test_search_web.py
│   ├── test_synthesize.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── styles.css
│   ├── package.json
│   └── vite.config.js
├── docs/
│   └── images/
├── Data/
├── docker-compose.yml
└── README.md
```

---

## ✅ 4. Các Công Việc Đã Hoàn Thành

### 4.1. Backend fact-check workflow

- Đã hoàn thiện workflow LangGraph:
  - `extract`
  - `retrieve_internal`
  - `judge_internal`
  - `search_web`
  - `judge_after_web`
  - `synthesize`
- Đã có API `POST /api/chat`
- Đã có API lịch sử chat:
  - `GET /api/chat/sessions`
  - `GET /api/chat/sessions/{session_id}`
  - `DELETE /api/chat/sessions/{session_id}`

### 4.2. Dữ liệu và database

- Đã dùng PostgreSQL + pgvector cho RAG nội bộ
- Đã có script seed dữ liệu
- Đã có lưu lịch sử session/message trong database
- Đã hỗ trợ filter session theo môn thể thao
- Đã hỗ trợ search session theo query người dùng đã hỏi

### 4.3. Frontend

Phần mới làm gần đây chủ yếu là frontend:

- Dựng giao diện chat một trang
- Empty state có chọn môn thể thao trước khi gửi query
- Sidebar lịch sử chat thật, lấy dữ liệu từ backend
- Dropdown filter lịch sử theo môn thể thao
- Search session theo claim/câu hỏi user đã nhập
- Xóa session
- Chuẩn hóa hiển thị category cho người dùng đọc được
- Hiển thị tiến trình kiểm chứng theo từng bước
- Đổi phần trả lời cuối sang dạng text block thay vì card assistant lớn
- Điều chỉnh UI dark theme đơn giản hơn để dễ đọc

---

## 🖼️ 5. Demo Giao Diện

### Sidebar lịch sử + search + filter

![Demo sidebar](docs/images/demo-result-view.jpg)

### Kết quả kiểm chứng + nguồn liên quan

![Demo result](docs/images/demo-session-list.jpg)

---

## 🚀 6. Các Bước Tiếp Theo (Next Steps)

### 6.1. Hoàn thiện frontend

- [ ] Tinh chỉnh UI/UX của sidebar, search và progress
- [ ] Nối progress với stream/event thật từ backend thay vì mô phỏng theo thời gian
- [ ] Tối ưu hiển thị kết quả dài, sources và sub-claims trên mobile
- [ ] Bổ sung thao tác nhanh như clear search, highlight từ khóa match

### 6.2. Cải thiện database

- [ ] Tối ưu truy vấn search session theo query
- [ ] Rà soát index cho `chat_sessions`, `chat_messages`, bảng knowledge base
- [ ] Chuẩn hóa thêm metadata bài báo để retrieval chính xác hơn
- [ ] Cải thiện backup/restore và quy trình chia sẻ DB sang máy khác

### 6.3. Cải thiện chất lượng fact-check

- [ ] Tiếp tục tinh chỉnh prompt extract / judge / synthesize
- [ ] Cải thiện ranking evidence nội bộ
- [ ] Cải thiện lọc kết quả Tavily theo từng môn thể thao
- [ ] Tạo bộ claim đánh giá chuẩn cho `SUPPORTED / REFUTED / NEI`

---

## ▶️ 7. Chạy Thử Project

### 7.1. Điều kiện cần

- Python 3.11+
- Node.js 20+
- Docker Desktop
- API keys:
  - `GEMINI_API_KEY`
  - `GROQ_API_KEY`
  - `TAVILY_API_KEY`

### 7.2. Clone project

```powershell
git clone <repo-url>
cd D:\code\DoAn
```

### 7.3. Tạo file môi trường cho backend

```powershell
cd D:\code\DoAn\backend
Copy-Item .env.example .env
```

Điền giá trị thật vào `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fakeguard
```

### 7.4. Khởi động PostgreSQL + pgvector

```powershell
cd D:\code\DoAn
docker compose up -d
docker compose ps
```

### 7.5. Cài backend

```powershell
cd D:\code\DoAn\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 7.6. Chuẩn bị dữ liệu

Có 2 cách:

#### Cách A - Restore từ backup DB

```powershell
docker cp D:\code\DoAn\backup\fakeguard.dump doan-db-1:/tmp/fakeguard.dump
docker exec -it doan-db-1 bash -lc "pg_restore -U postgres -d fakeguard --clean --if-exists /tmp/fakeguard.dump"
```

#### Cách B - Seed từ đầu

```powershell
cd D:\code\DoAn\backend
python scripts\seed_kb.py
```

### 7.7. Chạy backend

```powershell
cd D:\code\DoAn\backend
uvicorn app.main:app --reload
```

URL kiểm tra:
- Swagger docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Chat API: `POST /api/chat`

### 7.8. Chạy frontend

Mở terminal khác:

```powershell
cd D:\code\DoAn\frontend
npm install
npm run dev
```

Frontend local:
- [http://127.0.0.1:5173/](http://127.0.0.1:5173/)

---

## 🧪 8. Kiểm Thử

### 8.1. Test Chat API

```powershell
cd D:\code\DoAn\backend
python -X utf8 test_chat.py
```

### 8.2. Test graph bằng fake nodes

```powershell
cd D:\code\DoAn\backend
python -X utf8 test_graph.py
```

### 8.3. Chạy prototype graph thật

```powershell
cd D:\code\DoAn\backend
python -X utf8 test_graph_with_real_services.py --stage full
```

### 8.4. Test từng node

```powershell
cd D:\code\DoAn\backend
python -X utf8 test_extract.py
python -X utf8 test_judge.py
python -X utf8 test_rag.py
python -X utf8 test_search_web.py
python -X utf8 test_synthesize.py
```

---

## 📝 9. Ghi Chú

- `New chat` hiện chỉ reset UI, không tạo session rỗng
- Session chỉ được tạo khi user gửi query đầu tiên
- Tiến trình “đang kiểm chứng” ở frontend hiện là tiến trình sản phẩm theo bước, không phải chain-of-thought thô của model
- Nếu frontend báo `Failed to fetch`, kiểm tra backend còn chạy ở cổng `8000` hay không
