"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Core application settings."""

    # App
    APP_NAME: str = "CyberBuddy"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database — PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cyberbuddy"

    # Milvus Vector Database
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "it_knowledge"
    MILVUS_DIMENSION: int = 1024  # BAAI/bge-large-zh-v1.5 dimension

    # LLM
    LLM_MODEL: str = "deepseek-v4-pro"
    LLM_API_KEY: Optional[str] = "sk-eb21576b2d904a60b439d778c81f3f82"
    LLM_BASE_URL: Optional[str] = "https://api.deepseek.com"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"

    # Redis (for Celery / async queue)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
