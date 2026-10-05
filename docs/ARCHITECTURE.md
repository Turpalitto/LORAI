# ARCHITECTURE
Backend FastAPI (app/main.py) → Ingestion (pdf_loader/table_parser/icd10/llm_structurer/pipeline) →
Knowledge (SQLAlchemy Document + VectorStore Chroma/TF-IDF-fallback) →
RAG (intent → retrieval top-k → threshold → prompt → Mock/OpenAICompatible → anti-hallucination проверка чисел) →
Features (dosage/diff/checklist/templates/referral) → JWT (admin/doctor) + slowapi rate-limit.
Frontend React+Vite (chat + протоколы). БД: SQLite локально / Postgres в docker. Векторы: ./data/vector_store.
Новое (аудит-3): POST /search-protocol (DB-only), POST /admin/upload-pdf (алиас), PATCH /admin/documents/{id} (админ), домен-гейт has_lor_signal в should_refuse, /history и /admin/documents под JWT+ролями, дедуп загрузок.
