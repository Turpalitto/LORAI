# USER_GUIDE
Дисклеймер: инструмент справочный. Решение принимает врач. Не вводите ПДн.
1. `scripts/run_local.bat` → http://localhost:8000/docs, frontend — `npm run dev`.
2. Логин: admin@lorai.local / admin123 (админ), doctor@lorai.local / doctor123 (врач).
3. Чат: вопрос → ответ со ссылками [Документ, Раздел, Стр.] или честный отказ.
4. Протоколы: /protocols?q=отит — точный текст без LLM.
5. Дозы: POST /dosage {weight_kg, mg_per_kg, max_mg}.
# ADMIN_GUIDE
- Новые PDF: кинуть в корень или data/raw_pdfs → `python scripts/ingest_pdf.py .`
- Проверка: GET /admin/documents (Bearer admin).
- Real LLM: в .env LLM_PROVIDER=openai, LLM_API_KEY=..., LLM_MODEL=..., LLM_BASE_URL=... (OpenRouter/vLLM — тоже).
- Порог: LLM_THRESHOLD (0.12 TF-IDF / 0.75 embeddings).
