# 📊 Tài Liệu Dữ Liệu — FakeGuard (Sports Agentic RAG)

## 1. Giới Thiệu

FakeGuard là hệ thống **Agentic RAG** (Retrieval-Augmented Generation) chuyên biệt phát hiện tin giả Thể thao. Dự án sử dụng dữ liệu tin tức thể thao thật được thu thập từ các chuyên trang uy tín làm **Knowledge Base** (cơ sở tri thức) cho hệ thống RAG.

### Các file dữ liệu chính:

| File | Mô tả | Số bài |
|------|--------|--------|
| `real_news_prepared.csv` | Dữ liệu gốc đã làm sạch, có thêm cột ID | ~10,885 bài |
| `real_news.csv` | Dữ liệu crawl ban đầu | ~10,885 bài |

### Cấu trúc mỗi bài báo (CSV Schema - `real_news_prepared.csv`):

| Cột | Mô tả | Ví dụ |
|-----|--------|-------|
| `id` | UUID duy nhất của bài | e6b0... |
| `stt` | Số thứ tự | 1, 2, 3... |
| `category` | Thể loại thể thao | bong-da, bong-ro, bong-chay, tennis |
| `title` | Tiêu đề bài báo | "Thắng dễ Alcaraz, Machac..." |
| `summary` | Tóm tắt | Đoạn mô tả ngắn |
| `publish_date` | Ngày đăng | 22/04/2026 18:29 GMT+7 |
| `url` | Link gốc bài viết | https://webthethao.vn/... |
| `domain` | Tên miền nguồn | webthethao.vn |
| `content` | Nội dung đầy đủ | Toàn bộ nội dung bài báo |
| `language` | Ngôn ngữ | vi, en |

---

## 2. Cách Thức Thu Thập Dữ Liệu (Crawling)

### Công nghệ sử dụng:
- **Python** + **httpx** (HTTP async client) + **BeautifulSoup** (HTML parser)
- Cơ chế Deduplication: Lưu các URL đã crawl (`seen_urls`) để tránh lấy trùng ở các lần chạy sau.

### Các nguồn chuyên biệt:
- **Tennis:** `perfect-tennis.com`
- **Bóng đá & Thể thao chung:** `webthethao.vn`
- **Bóng rổ (NBA/VBA):** `sportando.basketball`
- **Bóng chày (MLB):** `mlbtraderumors.com`

---

## 3. Tổng Hợp Nguồn Tin & Số Bài Báo

*Dựa trên tập dữ liệu đã thu thập mới nhất (`real_news.csv`)*

### 3.1. Theo thể loại (Category)

| Thể loại | Số bài | Tỷ lệ |
|-----------|--------|-------|
| Bóng đá (`bong-da`) | 4,217 | 38.7% |
| Bóng rổ (`bong-ro`) | 3,590 | 33.0% |
| Bóng chày (`bong-chay`) | 1,895 | 17.4% |
| Tennis (`tennis`) | 1,183 | 10.9% |
| **Tổng** | **10,885** | **100%** |

---

## 4. Các Bước Xử Lý Dữ Liệu Đã Thực Hiện

### Bước 1: Thu thập (Crawling)
- Lấy thông tin từ các trang tin chuyên biệt về Thể thao.
- Phát hiện URL đã có và bỏ qua tự động (Deduplicate dựa trên URL).

### Bước 2: Chuẩn bị cho VectorDB (Mới cập nhật)
- Kiểm tra tính duy nhất qua trường `url`.
- Bổ sung trường UUID (`id`) để theo dõi khi nạp vào pgvector.
- Xuất ra file `real_news_prepared.csv`.

### Bước 3: Chunking (Dự kiến)
- Dùng **LangChain RecursiveCharacterTextSplitter**.
- Sẽ sử dụng `chunk_size = 800`, `chunk_overlap = 100`.
- Các chunk sẽ mang theo Metadata chi tiết (`url`, `category`, `domain`, v.v.) để phục vụ RAG.

### Bước 4: Embedding & Seed KB (Đang triển khai)
- Model: **`paraphrase-multilingual-MiniLM-L12-v2`** (SentenceTransformers).
- Vector dimension: **384**.
- Chạy batch import vào pgvector thông qua `backend/scripts/seed_kb.py`.

---

## 5. Kiến Trúc Database

### Docker Compose:
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
      - ./Data/pg_vector_data:/var/lib/postgresql/data
```

### Schema dự kiến bảng `knowledge_base` (Hỗ trợ Agentic RAG):
```sql
CREATE TABLE knowledge_base (
    id          VARCHAR PRIMARY KEY,  -- Từ cột 'id'
    url         VARCHAR UNIQUE,       -- Đảm bảo không trùng lặp
    domain      VARCHAR(255),
    title       TEXT NOT NULL,
    publish_date VARCHAR(50),
    category    VARCHAR(100),
    content     TEXT NOT NULL,
    embedding   VECTOR(384)           -- pgvector
);
```

---

## 6. Luồng Truy Xuất Dữ Liệu (Retrieval)

Dữ liệu sẽ được phục vụ cho Pipeline RAG 3-Node:
1. **Node 1 (Expand Query):** Dùng LLM trích xuất Keyword và Entity thể thao.
2. **Node 2 (Hybrid Retrieve):**
   - Tra cứu Vector similarity dựa trên trường `embedding`.
   - Tra cứu ILIKE khớp `title`/`content` với Entity.
   - Rerank kết quả dựa trên Entity Heuristic (ưu tiên bài báo có nhiều từ khóa Entity ở title).
3. **Node 3 (Fact-Check):** Đưa các đoạn text tốt nhất vào LLM để suy luận xác thực.
