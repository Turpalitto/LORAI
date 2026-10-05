# LORAI — ассистент ЛОР-врача (strict RAG по клинрекомендациям)
Запуск без Docker: `scripts/run_local.bat` (SQLite + локальные векторы).
С Docker: `docker-compose up --build`.
Переиндексация: `python scripts/ingest_pdf.py .` (22 КР уже загружены).
Ключ LLM: скопировать .env.example→.env, вписать LLM_API_KEY + LLM_PROVIDER=openai.
API docs: http://localhost:8000/docs
