"""
@brief Script nạp dữ liệu báo chí vào Vector Database (PostgreSQL + pgvector)
@details Đọc CSV -> Chunk text -> Embed -> Lưu vào DB
Schema mỗi bài: category, title, summary, publish_date, url, domain, content
"""
import asyncio
import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
import sys
import os
import io

# Fix encoding Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ["HF_HOME"] = "d:/code/DoAn/hf_cache"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db, AsyncSessionLocal, KnowledgeBase
from app.services.embedding import embed_batch

# Đọc cả 2 file: dữ liệu gốc + dữ liệu crawl mới
CSV_FILES = [
    "../Data/real_news.csv",  # Dữ liệu Thể thao tổng hợp
]
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

from sqlalchemy import select

def build_text(row: pd.Series) -> str:
    """Ghép title + summary + content thành 1 đoạn văn để embed."""
    parts = []
    if pd.notna(row.get("title")) and str(row["title"]).strip():
        parts.append(str(row["title"]).strip())
    if pd.notna(row.get("summary")) and str(row["summary"]).strip():
        parts.append(str(row["summary"]).strip())
    if pd.notna(row.get("content")) and str(row["content"]).strip():
        parts.append(str(row["content"]).strip())
    return "\n".join(parts)

async def run_seed():
    print("⏳ 1. Khởi tạo bảng CSDL...")
    await init_db()

    # Lấy danh sách URL đã có trong DB để tránh chunking lặp
    existing_urls = set()
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(KnowledgeBase.url))
            for row in result.all():
                if row[0]:
                    existing_urls.add(row[0])
        print(f"   [DB] Đã có {len(existing_urls)} bài viết (unique urls) trong DB.")
    except Exception as e:
        print(f"   [DB] Không thể lấy danh sách bài viết cũ: {e}")

    # Đọc và gộp tất cả file CSV có sẵn
    dfs = []
    for path in CSV_FILES:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"   Đọc {len(df)} dòng từ {path}")
            dfs.append(df)
        else:
            print(f"   [SKIP] Không tìm thấy {path}")

    if not dfs:
        print("❌ Không có file dữ liệu nào!")
        return

    all_df = pd.concat(dfs, ignore_index=True)

    # Loại bỏ bài trùng lặp theo url (nếu có cột url)
    if "url" in all_df.columns:
        before = len(all_df)
        all_df = all_df.drop_duplicates(subset=["url"])
        print(f"   Sau khi lọc trùng: {len(all_df)} bài (bỏ {before - len(all_df)} bài trùng)")

    print(f"\n✂️ 2. Cắt nhỏ nội dung {len(all_df)} bài báo thành chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    records = []
    for _, row in all_df.iterrows():
        title = str(row.get("title", ""))
        
        url = str(row.get("url", ""))
        
        # BỎ QUA NẾU BÀI NÀY ĐÃ CÓ TRONG DATABASE
        if url and url in existing_urls:
            continue
            
        full_text = build_text(row)
        if len(full_text) < 50:
            continue  # Bỏ bài quá ngắn

        chunks = splitter.split_text(full_text)
        for chunk in chunks:
            records.append({
                "domain":       str(row.get("domain", "")),
                "url":          str(row.get("url", "")),
                "title":        title[:200],
                "publish_date": str(row.get("publish_date", "")),
                "category":     str(row.get("category", "")),
                "language":     str(row.get("language", "vi")),
                "content":      chunk,
                "label":        1,
            })

    total = len(records)
    print(f"   -> Sinh ra {total} chunks MỚI để embed.\n")

    if total == 0:
        print("✅ Tất cả dữ liệu đã có trong Database. Không cần nạp thêm!")
        return
    print(f"🧠 3. Embedding và lưu vào Database (batch 64)...")

    BATCH = 64
    saved = 0
    for i in range(0, total, BATCH):
        batch = records[i:i + BATCH]
        texts = [b["content"] for b in batch]

        # Embedding (chạy trên CPU, không cần DB connection)
        vectors = embed_batch(texts)

        # Mở session MỚI cho mỗi batch → tránh timeout connection
        for attempt in range(3):  # Retry tối đa 3 lần
            try:
                async with AsyncSessionLocal() as session:
                    db_objs = [
                        KnowledgeBase(
                            domain=b["domain"],
                            url=b["url"],
                            title=b["title"],
                            publish_date=b["publish_date"],
                            category=b["category"],
                            language=b["language"],
                            label=b["label"],
                            content=b["content"],
                            embedding=vectors[j],
                        )
                        for j, b in enumerate(batch)
                    ]
                    session.add_all(db_objs)
                    await session.commit()
                saved += len(batch)
                pct = saved * 100 // total
                print(f"   [{pct:3d}%] Đã lưu {min(i + BATCH, total)}/{total} chunks...")
                break  # Thành công, thoát retry
            except Exception as e:
                if attempt < 2:
                    print(f"   ⚠️ Lỗi DB (retry {attempt+1}/3): {e}")
                    await asyncio.sleep(2)
                else:
                    print(f"   ❌ Lỗi DB sau 3 lần thử: {e}")
                    raise

    print(f"\n✅ HOÀN TẤT! Đã lưu {saved}/{total} chunks vào Vector Database.")

if __name__ == "__main__":
    asyncio.run(run_seed())
