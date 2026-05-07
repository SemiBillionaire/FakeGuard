"""
@brief Công cụ Embedding tiếng Việt sử dụng SentenceTransformers
@details Model: paraphrase-multilingual-MiniLM-L12-v2 - phục vụ vector hóa Tiếng Việt
"""
from sentence_transformers import SentenceTransformer
import os

# Ổ C của bạn đang bị Đầy (Chỉ còn 8MB trống), nên tôi chuyển thư mục lưu Model sang ổ D
os.environ["HF_HOME"] = "d:/code/DoAn/hf_cache"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Load model khi ứng dụng khởi chạy
# Model này nhẹ (~450MB) và chạy tốt trên CPU máy cá nhân
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

def embed(text: str) -> list[float]:
    """
    @brief Hàm biểu diễn 1 đoạn text tiếng Việt dạng string thành vector 384 dimensions
    @param text: đoạn text đầu vào
    @return list các tham số float của vector
    """
    return model.encode(text).tolist()

def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    @brief Vector hóa hàng loạt text để tăng tốc độ xử lý Batch
    """
    return model.encode(texts).tolist()
