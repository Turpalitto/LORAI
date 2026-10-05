# ARCHITECTURE
Backend FastAPI (app/main.py) → Ingestion (pdf_loader/table_parser/icd10/llm_structurer/pipeline) →
Knowledge (SQLAlchemy Document + VectorStore Chroma/TF-IDF-fallback) →
RAG (intent → retrieval top-k → threshold → prompt → Mock/OpenAICompatible → anti-hallucination проверка чисел) →
Features (dosage/diff/checklist/templates/referral) → JWT (admin/doctor) + slowapi rate-limit.
Frontend React+Vite (chat + протоколы). БД: SQLite локально / Postgres в docker. Векторы: ./data/vector_store.
