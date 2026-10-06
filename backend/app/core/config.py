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
    VECTOR_BACKEND: str = "tfidf"  # tfidf | chroma (см. DECISIONS #20)
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    JWT_SECRET: str = "change-me-in-production-please"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ADMIN_EMAIL: str = "admin@lorai.local"
    ADMIN_PASSWORD: str = "admin123"
    # LORAI_ENV=production запрещает дефолтный JWT_SECRET (fail-fast в security.py)
    LORAI_ENV: str = "development"
    # Врач-аккаунт создаётся только если обе переменные заданы (дефолтного нет)
    LORAI_DOCTOR_EMAIL: str = ""
    LORAI_DOCTOR_PASSWORD: str = ""
    # CORS allowlist web-клиентов (native-клиенты без Origin не затрагиваются)
    LORAI_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
DISCLAIMER = "Инструмент носит вспомогательный справочный характер. Решение принимает врач."
