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
    # Дефолт — измеренная рабочая конфигурация (embeddings), а не tfidf:
    # прежний дефолт давал установке «из коробки» заметно худший поиск, чем
    # в замерах. Если модель недоступна, стор честно откатывается на TF-IDF
    # с причиной в /admin/health (DECISIONS #20, #26).
    VECTOR_BACKEND: str = "embeddings"  # tfidf | embeddings | chroma
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    # Кэш модели держим внутри проекта: стенд самодостаточен и не зависит от
    # прав на ~/.cache (в песочнице запись туда запрещена).
    EMBEDDING_CACHE_DIR: str = str(ROOT_DIR / "data" / "hf_cache")
    # Во сколько раз приоритетнее чанк нужного раздела (лечение/диагностика).
    # 1.0 — выключить маршрутизацию по разделам. Калибруется замером:
    # scripts/eval_retrieval.py (см. docs/RETRIEVAL_EVAL.md).
    SECTION_BOOST: float = 1.15
    # Во сколько раз приоритетнее чанк нозологии, которую распознали в вопросе
    # (rag/retriever.nosology_hint). 1.0 — выключить. Значение измерено на
    # hold-out: косинусы соседних протоколов отличаются на 0.005–0.01, поэтому
    # без явного приоритета «лечение синусита» встаёт выше «лечения отита».
    NOSOLOGY_BOOST: float = 1.15
    # Сколько обзорных (general) чанков допустимо в топ-k, когда вопрос про
    # конкретный раздел: иначе дубли-обзоры вытесняют нужный раздел.
    GENERAL_CHUNK_CAP: int = 2
    # Вес лексической составляющей поверх эмбеддингов (калибруется замером):
    # клинически соседние темы (острый/хронический отит) ловятся точным термином.
    HYBRID_WEIGHT: float = 0.15
    # Реранкер: переупорядочивает топ кандидатов кросс-энкодером. По умолчанию
    # ВЫКЛЮЧЕН — включается только после замера на hold-out (docs/RETRIEVAL_EVAL.md).
    # Модель — русскоязычный кросс-энкодер на rubert-base, обученный на mMARCO.
    RERANK_BACKEND: str = "off"  # off | cross
    RERANK_MODEL: str = "DiTy/cross-encoder-russian-msmarco"
    # Сколько кандидатов отдаём реранкеру: больше — точнее и медленнее.
    RERANK_TOP_N: int = 20
    RERANK_BATCH: int = 16
    # Вес кросс-энкодера в итоговом порядке (0 — только косинус, 1 — только
    # реранкер). Чистый реранкер поднимает recall, но роняет MRR: он тянет
    # нужный протокол в топ-6, сдвигая лучший чанк вниз. Смесь калибруется
    # замером на hold-out — см. docs/RETRIEVAL_EVAL.md.
    RERANK_BLEND: float = 0.3
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
    # Политика хранения. Тексты клинических запросов в БД бессрочно — лишний
    # риск: ПДн-фильтр на входе не абсолютен. 0 — не чистить (не рекоменуется).
    QUERY_RETENTION_DAYS: int = 90
    AUDIT_RETENTION_DAYS: int = 365
    # Формат логов: text (человеку) | json (Loki/ELK: одна строка — одна запись).
    LOG_FORMAT: str = "text"
    # За обратным прокси реальный IP приходит в X-Forwarded-For. Без этого
    # лимитер и аудит видят один адрес прокси на всех врачей (30/мин на всех).
    TRUST_PROXY_HEADERS: bool = False
    APP_VERSION: str = "1.10.0"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
DISCLAIMER = "Инструмент носит вспомогательный справочный характер. Решение принимает врач."
