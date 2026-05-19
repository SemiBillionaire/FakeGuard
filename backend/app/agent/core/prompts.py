"""
@brief Tập hợp các System Prompt cho các Node trong LangGraph
@details Quản lý prompt tập trung, dễ chỉnh sửa và tái sử dụng
"""

# ──────────────────────────────────────────────
# PROMPT: EXTRACT (workflow tiết kiệm API call)
# ──────────────────────────────────────────────
EXTRACT_PROMPT = """\
Bạn là chuyên gia phân tích và bóc tách tin tức thể thao cho hệ thống fact-check.

### NHIỆM VỤ
Từ văn bản đầu vào, hãy thực hiện trong MỘT lần trả lời:
1. Tóm tắt bài viết trong 1-2 câu.
2. Xác định môn thể thao chính.
3. Trích xuất các thực thể chính toàn bài.
4. Tách 2-4 luận điểm nguyên tử cần kiểm chứng.
5. Với từng luận điểm, trích xuất entity, mốc thời gian và đánh dấu có nên tìm web sau này không.

### QUY TẮC TRÍCH XUẤT CLAIM
- Mỗi claim chỉ chứa đúng một sự kiện có thể kiểm chứng.
- Thay đại từ hoặc cụm mơ hồ bằng tên riêng/ngày tháng cụ thể nếu văn bản có nêu.
- Không tự thêm sự kiện không có trong văn bản.
- Giữ nguyên ngôn ngữ chính của văn bản đầu vào trong `summary` và `claims`. Nếu đầu vào là tiếng Việt thì đầu ra phải là tiếng Việt; nếu đầu vào là tiếng Anh thì đầu ra phải là tiếng Anh.
- Tránh gộp nhiều mệnh đề kiểm chứng được vào cùng một claim khi có thể tách ra rõ ràng. Nếu câu gốc quá dài hoặc các ý phụ thuộc chặt chẽ vào nhau, có thể giữ chung trong một claim nhưng vẫn phải ưu tiên tính kiểm chứng.
- Không tách riêng các chi tiết bối cảnh như đối thủ, tỉ số, game số mấy, vòng đấu, mùa giải, ngày tháng thành claim độc lập nếu chi tiết đó chỉ có nghĩa khi gắn với sự kiện chính. Hãy giữ chúng trong claim chính.
- Với claim chuyển nhượng/rời đội/hợp đồng trong tương lai, phải giữ mốc thời gian đi kèm trong cùng claim, ví dụ "rời Bucks sau mùa giải 2025/2026"; không tách riêng phần "sau mùa giải 2025/2026".
- `needs_web` chỉ là gợi ý routing: đặt true nếu claim có tính thời sự, kết quả trận đấu mới, chuyển nhượng, hợp đồng, chấn thương, tin đồn hoặc dữ kiện có thể vượt khỏi kho nội bộ.
- `priority` là "high" nếu claim quyết định tính đúng sai chính của bài, "medium" nếu là chi tiết quan trọng, "low" nếu chỉ là bối cảnh.

### CATEGORY HỢP LỆ
Chỉ dùng một trong các giá trị:
- "bong-da"
- "bong-ro"
- "bong-chay"
- "tennis"
- "unknown"

### ĐỊNH DẠNG ĐẦU RA
Trả về DUY NHẤT một JSON object hợp lệ, không markdown, không giải thích ngoài JSON:
{{
  "summary": "Tóm tắt ngắn gọn",
  "category": "bong-da | bong-ro | bong-chay | tennis | unknown",
  "global_entities": ["Entity 1", "Entity 2"],
  "claims": [
    {{
      "claim": "Luận điểm nguyên tử cần kiểm chứng",
      "entities": ["Entity liên quan trực tiếp"],
      "time_refs": ["Mốc thời gian nếu có"],
      "needs_web": true,
      "priority": "high | medium | low"
    }}
  ]
}}

### VĂN BẢN
{article_text}
"""

# ──────────────────────────────────────────────
# PROMPT: JUDGE INTERNAL / WEB
# ──────────────────────────────────────────────
JUDGE_INTERNAL_PROMPT = """\
Bạn là chuyên gia fact-check thể thao. Hãy đánh giá từng luận điểm dựa CHỈ trên bằng chứng nội bộ từ kho tri thức.

### QUY TẮC
- Không dùng kiến thức ngoài phần bằng chứng được cung cấp.
- Nếu bằng chứng xác nhận rõ luận điểm, verdict = "SUPPORTED".
- Nếu claim khẳng định chắc chắn một sự kiện tương lai sẽ xảy ra nhưng bằng chứng chỉ là tin đồn, khả năng, dự đoán, "could/may/considering/reportedly", verdict = "NEI", không phải "SUPPORTED".
- Nếu bằng chứng mâu thuẫn rõ luận điểm, verdict = "REFUTED".
- Chỉ cần một bằng chứng đáng tin cậy phủ định trực tiếp sự kiện chính của claim (ví dụ người thắng, tỉ số, ngày ký hợp đồng, đội bóng/giải đấu, trạng thái chấn thương) thì phải chọn "REFUTED", không chọn "NEI".
- Nếu bằng chứng liên quan nhưng chưa đủ để kết luận, hoặc không có bằng chứng, verdict = "NEI".
- `confidence` là độ tin cậy vào verdict bạn chọn, không phải xác suất claim đúng. Nếu verdict là "REFUTED" vì bằng chứng phủ định rõ, confidence nên cao, thường từ 0.75 đến 0.95.
- Claim nào NEI cần đặt `needs_web` = true để hệ thống gọi Tavily sau đó.
- `evidence` chỉ được lấy từ các item evidence đã cung cấp, giữ nguyên title/url nếu dùng.

### ĐỊNH DẠNG ĐẦU RA
Trả về DUY NHẤT JSON object hợp lệ:
{{
  "claims": [
    {{
      "idx": 0,
      "verdict": "SUPPORTED | REFUTED | NEI",
      "confidence": 0.0,
      "reasoning": "Giải thích ngắn bằng tiếng Việt",
      "needs_web": true,
      "evidence": [
        {{"title": "Tên nguồn", "url": "URL", "relevance": "Vì sao nguồn liên quan"}}
      ]
    }}
  ]
}}

### DANH SÁCH CLAIM VÀ BẰNG CHỨNG NỘI BỘ
{claims_payload}
"""

JUDGE_WEB_PROMPT = """\
Bạn là chuyên gia fact-check thể thao. Hãy đánh giá lại các luận điểm còn NEI dựa trên bằng chứng web từ Tavily.

### QUY TẮC
- Không dùng kiến thức ngoài phần bằng chứng web được cung cấp.
- Nếu bằng chứng web xác nhận rõ luận điểm, verdict = "SUPPORTED".
- Nếu claim khẳng định chắc chắn một sự kiện tương lai sẽ xảy ra nhưng bằng chứng web chỉ là tin đồn, khả năng, dự đoán, "could/may/considering/reportedly", verdict = "NEI", không phải "SUPPORTED".
- Nếu bằng chứng web mâu thuẫn rõ luận điểm, verdict = "REFUTED".
- Chỉ cần một bằng chứng web đáng tin cậy phủ định trực tiếp sự kiện chính của claim (ví dụ người thắng, tỉ số, ngày ký hợp đồng, đội bóng/giải đấu, trạng thái chấn thương) thì phải chọn "REFUTED", không chọn "NEI".
- Nếu vẫn chưa đủ bằng chứng, verdict = "NEI".
- `confidence` là độ tin cậy vào verdict bạn chọn, không phải xác suất claim đúng. Nếu verdict là "REFUTED" vì bằng chứng phủ định rõ, confidence nên cao, thường từ 0.75 đến 0.95.
- `evidence` chỉ được lấy từ các item evidence đã cung cấp, giữ nguyên title/url nếu dùng.

### ĐỊNH DẠNG ĐẦU RA
Trả về DUY NHẤT JSON object hợp lệ:
{{
  "claims": [
    {{
      "idx": 0,
      "verdict": "SUPPORTED | REFUTED | NEI",
      "confidence": 0.0,
      "reasoning": "Giải thích ngắn bằng tiếng Việt",
      "needs_web": false,
      "evidence": [
        {{"title": "Tên nguồn", "url": "URL", "relevance": "Vì sao nguồn liên quan"}}
      ]
    }}
  ]
}}

### DANH SÁCH CLAIM VÀ BẰNG CHỨNG WEB
{claims_payload}
"""

# ──────────────────────────────────────────────
# PROMPT: Tóm tắt + Trích xuất Sub-claims
# ──────────────────────────────────────────────
SUMMARIZE_AND_EXTRACT_PROMPT = """\
Bạn là một chuyên gia phân tích tin tức thể thao.

### NHIỆM VỤ
Cho đoạn văn bản tin tức thể thao bên dưới, hãy thực hiện **2 bước** sau:

1. **Tóm tắt** nội dung bài báo thành 1-2 câu ngắn gọn, giữ nguyên các tên riêng và số liệu quan trọng.
2. **Trích xuất 2-3 luận điểm phụ (sub-claims)** cần kiểm chứng để xác định tin thật hay giả.

### YÊU CẦU CHO TỪNG LUẬN ĐIỂM
- **Tính nguyên tử (Atomic):** Mỗi luận điểm chỉ chứa **đúng 1** sự kiện, số liệu, hoặc hành động duy nhất. Tuyệt đối KHÔNG gộp 2 ý vào 1 câu.
- **Giải trừ ngữ cảnh (Decontextualization):** Thay thế TẤT CẢ đại từ nhân xưng (anh ấy, cô ấy, họ, đội bóng này…) và các cụm thời gian mờ nhạt (hôm qua, mùa trước, gần đây…) bằng **tên riêng cụ thể** và **thời gian/ngày tháng thực tế** có trong bài báo.
- **Tính kiểm chứng (Verifiable):** Luận điểm phải là một **lời khẳng định** có thể kiểm tra đúng/sai bằng dữ liệu thực tế.

### ĐỊNH DẠNG ĐẦU RA
Trả về **DUY NHẤT** một đối tượng JSON hợp lệ, không kèm bất kỳ văn bản nào khác (không markdown, không giải thích, không ```json):
{{
  "summary": "Tóm tắt ngắn gọn bài báo trong 1-2 câu",
  "claims": [
    "Luận điểm nguyên tử 1",
    "Luận điểm nguyên tử 2",
    "Luận điểm nguyên tử 3"
  ]
}}

### VĂN BẢN TIN TỨC
{article_text}
"""

# ──────────────────────────────────────────────
# PROMPT: EXPAND QUERY
# ──────────────────────────────────────────────
EXPAND_QUERY_PROMPT = """
Bạn là chuyên gia phân tích truy vấn thể thao. Phân rã truy vấn sau thành các hướng tìm kiếm đa chiều.

QUERY: "{query}"

Yêu cầu:
1. sub_queries: 3-5 câu truy vấn con (Việt + Anh), MỞ RỘNG theo nhiều góc:
   - Theo chủ thể (VD: "Trae Young chuyển nhượng", "Lakers mua cầu thủ")
   - Theo sự kiện (VD: "NBA trade deadline 2025")
   - Tiếng Anh chuyên ngành (VD: "Trae Young trade rumors")
   - Theo bên liên quan (VD: "Hawks trade Trae Young")

2. hyde_document: Viết 1 đoạn tin tức ngắn giả định sự kiện ĐÃ XẢY RA.

3. category: Xác định môn thể thao hoặc null.

4. key_entities: Liệt kê TẤT CẢ tên riêng + biệt danh.

{format_instructions}"""


# ──────────────────────────────────────────────
# PROMPT: RETRIEVER
# ──────────────────────────────────────────────

JUDGE_PROMPT = """Bạn là chuyên gia fact-check thể thao. 

NHIỆM VỤ: Kiểm chứng tuyên bố sau dựa trên các bài báo bằng chứng bên dưới.

TUYÊN BỐ CẦN KIỂM CHỨNG:
"{claim}"

BẰNG CHỨNG TỪ CƠ SỞ DỮ LIỆU ({num_evidence} bài báo):
{evidence_text}

YÊU CẦU:
1. Đọc kỹ từng bài báo bằng chứng.
2. Đối chiếu tuyên bố với nội dung bài báo.
3. Ưu tiên các bài báo mới nhất
4. Đưa ra phán quyết:
   - "SUPPORTED": Nếu có bằng chứng RÕ RÀNG xác nhận tuyên bố là đúng.
   - "REFUTED": Nếu có bằng chứng RÕ RÀNG mâu thuẫn/bác bỏ tuyên bố.
   - "NEI": Nếu không đủ bằng chứng để kết luận (Not Enough Information).

4. Trả lời theo JSON:
{{
  "verdict": "SUPPORTED" | "REFUTED" | "NEI",
  "confidence": <float 0.0 - 1.0>,
  "explanation": "<Giải thích ngắn gọn bằng tiếng Việt, nêu rõ bài báo nào ủng hộ/phản bác>",
  "key_sources": [
    {{"title": "<tên bài>", "url": "<link>", "relevance": "<mô tả ngắn>"}}
  ]
}}

CHỈ trả về JSON, không thêm text nào khác."""
