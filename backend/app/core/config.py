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
    # Порог для эмбеддингов: у e5 своя шкала (0.84–0.91 даже на нерелевантном),
    # домены разделяет не скор, а домен-гейт — см. docs/RETRIEVAL_EVAL.md
    EMBEDDING_THRESHOLD: float = 0.75
    DATABASE_URL: str = f"sqlite:///{ROOT_DIR}/lorai.db"
    CHROMA_DIR: str = str(ROOT_DIR / "data" / "vector_store")
    VECTOR_BACKEND: str = "tfidf"  # tfidf | embeddings | chroma (DECISIONS #20, #26)
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    # Кэш модели держим внутри проекта: стенд самодостаточен и не зависит от
    # прав на ~/.cache (в песочнице запись туда запрещена).
    EMBEDDING_CACHE_DIR: str = str(ROOT_DIR / "data" / "hf_cache")
    # Во сколько раз приоритетнее чанк нужного раздела (лечение/диагностика).
    # 1.0 — выключить маршрутизацию по разделам. Калибруется замером:
    # scripts/eval_retrieval.py (см. docs/RETRIEVAL_EVAL.md).
    SECTION_BOOST: float = 1.15
    # Сколько обзорных (general) чанков допустимо в топ-k, когда вопрос про
    # конкретный раздел: иначе дубли-обзоры вытесняют нужный раздел.
    GENERAL_CHUNK_CAP: int = 2
    # Вес лексической составляющей поверх эмбеддингов (калибруется замером):
    # клинически соседние темы (острый/хронический отит) ловятся точным термином.
    HYBRID_WEIGHT: float = 0.0
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
