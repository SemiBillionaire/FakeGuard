from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    @brief Lớp cấu hình ứng dụng
    @details Load các biến môi trường từ file .env. Quản lý các keys cho LLM, DB, WebSearch
    """
    GOOGLE_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fakeguard"

    class Config:
        env_file = ".env"

settings = Settings()
