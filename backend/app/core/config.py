from pydantic_settings import BaseSettings
from pathlib import Path
# корень проекта: .../LORAI (не зависит от cwd запуска)
ROOT_DIR = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    LLM_API_KEY: str = ""
    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_THRESHOLD: float = 0.12
    DATABASE_URL: str = f"sqlite:///{ROOT_DIR}/lorai.db"
    CHROMA_DIR: str = str(ROOT_DIR / "data" / "vector_store")
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    JWT_SECRET: str = "change-me-in-production-please"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ADMIN_EMAIL: str = "admin@lorai.local"
    ADMIN_PASSWORD: str = "admin123"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
DISCLAIMER = "Инструмент носит вспомогательный справочный характер. Решение принимает врач."
