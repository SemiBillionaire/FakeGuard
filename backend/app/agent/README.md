# 🤖 Kiến Trúc & Hướng Dẫn FakeGuard Agent

Tài liệu này trình bày tổng quan cách thức hoạt động của mô hình Agentic RAG cho FakeGuard và mô tả chi tiết kiến trúc thư mục. Agent đóng vai trò như một "Điều tra viên AI", nhận tin đồn, tự phân rã, tự tìm kiếm bằng chứng và đưa ra phán quyết cuối cùng.

---

## 🎯 1. Tổng Quan Các Bước Hoạt Động Của RAG LLM

Quy trình kiểm chứng một bài báo/tin đồn sẽ đi qua **4 bước tuần tự** do LangGraph điều phối:

1. **Bước 1: Tóm tắt & Phân rã (Extraction)**
   - **Tóm tắt (Summarizer):** AI nhận một bài báo dài hoặc nội dung URL và tóm tắt lại các ý chính.
   - **Trích xuất luận điểm (Extractor):** Bóc tách bài tóm tắt thành các khẳng định cụ thể, độc lập (Sub-claims). *Ví dụ: "Hà Nội sẽ cấm xe máy vào năm 2026."*

2. **Bước 2: Kiểm chứng Lớp 1 - Nội bộ (RAG Retriever)**
   - Với mỗi luận điểm, Agent sẽ dùng `tools/rag_retriever.py` để tra cứu trong cơ sở dữ liệu `knowledge_base` (PostgreSQL + pgvector).
   - Agent đối chiếu bằng chứng với luận điểm và đưa ra 1 trong 3 trạng thái:
     - ✅ **SUPPORTED** (Tin chuẩn)
     - ❌ **REFUTED** (Tin giả)
     - ⚠️ **NEI** (Not Enough Information - Không đủ thông tin)

3. **Bước 3: Kiểm chứng Lớp 2 - Internet (Web Search)**
   - Nếu kết quả ở Lớp 1 trả về là **NEI** (Có thể do tin tức quá mới hoặc chưa từng có trong DB), Agent tự động kích hoạt `tools/searcher.py`.
   - Tìm kiếm trên Internet (qua Tavily API) lấy thông tin từ các trang báo uy tín.
   - Thực hiện đối chiếu lại một lần nữa để chốt trạng thái SUPPORTED/REFUTED/NEI.

4. **Bước 4: Tổng hợp & Phản hồi (Synthesizer)**
   - Agent gom tất cả các luận điểm đã được kiểm chứng.
   - Soạn thảo một báo cáo Fact-check bằng ngôn ngữ tự nhiên, minh bạch, có đính kèm đầy đủ link nguồn (URL) làm bằng chứng cho người dùng.

---

## 📂 2. Cấu Trúc Thư Mục Hệ Thống

Dưới đây là thiết kế kiến trúc cho folder `agent/`, tuân thủ chuẩn chia tách Logic và Tool của LangGraph:

```text
backend/app/agent/
│
├── README.md               # Tài liệu kiến trúc và luồng hoạt động
├── __init__.py
├── config.py               # Quản lý API Keys, config LLM, Tavily
├── state.py                # Định nghĩa AgentState (Pydantic/TypedDict) truyền giữa các Node
├── graph.py                # File cấu hình StateGraph của LangGraph, kết nối các Node
│
├── core/
│   ├── __init__.py
│   └── prompts.py          # Nơi lưu trữ tập trung MỌI Prompt (System Prompts)
│
├── tools/                  # Các công cụ mở rộng năng lực cho AI
│   ├── __init__.py
│   ├── rag_retriever.py    # Code chuyển query thành vector và tìm trong PostgreSQL
│   └── searcher.py         # Code tích hợp API tìm kiếm Internet (Tavily/Google)
│
└── nodes/                  # Các "Trạm kiểm soát" (Node) trong đồ thị LangGraph
    ├── __init__.py
    ├── summarizer.py       # Node 1: Tóm tắt bài báo đầu vào
    ├── extractor.py        # Node 2: Trích xuất các Sub-claims
    ├── verifier.py         # Node 3: Kiểm chứng từng Claim (dùng Tools)
    └── synthesizer.py      # Node 4: Viết báo cáo tổng hợp gửi về Frontend
```

---

## 🚀 3. Các Bước Khuyến Nghị Tiếp Theo (Next Steps)

Để hiện thực hóa kiến trúc trên, dưới đây là lộ trình lập trình theo thứ tự tối ưu:

### Phase 1: Xây dựng Bộ Công Cụ (Tools)
- **Code `tools/rag_retriever.py`:** Viết hàm nhận vào câu hỏi `string`, thực hiện embed và query trả về `Top K` documents từ PostgreSQL.
- **Code `tools/searcher.py`:** Đăng ký API Key của Tavily (Hoặc Google Search API) và viết hàm nhận query trả về nội dung tìm kiếm trên web.

### Phase 2: Xây dựng Node Mở Đầu (Extraction & Prompting)
- **Code `core/prompts.py`:** Viết các hướng dẫn (system prompts) chuẩn kỹ sư prompt (VD: "Bạn là một nhà báo điều tra... Không được bịa đặt... Phải trả về chuẩn JSON...").
- **Code `nodes/extractor.py`:** Sử dụng Gemini kết hợp `PydanticOutputParser` để bóc tách thông tin thành List các Sub-claims.

### Phase 3: Xây dựng Logic Đối Chiếu (Verification Node)
- **Code `nodes/verifier.py`:** Xây dựng vòng lặp cho mỗi Sub-claim:
  - Gọi Tool Lớp 1 (RAG). Hỏi LLM phán quyết.
  - Nếu phán quyết là NEI, gọi Tool Lớp 2 (Search). Hỏi LLM phán quyết lần cuối.
  - Cập nhật nhãn (SUPPORTED/REFUTED/NEI) vào `state.py`.

### Phase 4: Nối Đồ Thị và Khởi Chạy (LangGraph)
- **Code `graph.py`:** Map các Node lại với nhau (`add_node`), thiết lập Cạnh (`add_edge`), chỉ định điểm `START` và `END`.
- Tích hợp Graph vào file FastApi (`main.py`) để frontend có thể POST dữ liệu lên và lấy kết quả.
