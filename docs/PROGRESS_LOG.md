# PROGRESS_LOG
- Этап 0: скелет repo, .env.example, compose, requirements, config/security/logging. OK.
- Этап 1: ingestion (loader/tables/icd10/llm/pipeline). 22 PDF из «ЛОР КЛИНРЕКИ» → 22 OK high-confidence.
- Этап 2: SQLite + VectorStore(TF-IDF fallback) + repository + ingest CLI. OK.
- Этап 3: RAG + MockLLM + threshold 0.75→0.12 (DECISIONS #1). Проверка: релевант 0.23→ответ, нерелевант 0.08→отказ. OK.
- Этап 4: API 12 роутов. OK.
- Этап 5: frontend MVP (чат+поиск). Частично.
- Этап 6: JWT pbkdf2 (bcrypt backend отсутствовал → замена). OK.
- Этап 7: pytest 5/5 зелёные. OK.
- Этап 8-10: доки + FINAL_REPORT. OK.
