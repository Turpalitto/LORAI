# ADMIN_GUIDE
## Доступ
Логин администратора: admin@lorai.local / admin123 (сменить в .env: ADMIN_EMAIL/ADMIN_PASSWORD).
Роль врача: doctor@lorai.local / doctor123 — загрузка PDF запрещена (403).

## Загрузка новых КР
1. Вариант А (UI): Админ → войти → выбрать PDF → загрузка идёт в /admin/upload (лимит 50 МБ, проверка %PDF).
2. Вариант Б (CLI): положить PDF в корень или data/raw_pdfs → `python scripts/ingest_pdf.py .`
3. Проверка: GET /admin/documents с Bearer-токеном; поле needs_review=true → проверить вручную.

## Real LLM
В .env: LLM_PROVIDER=openai, LLM_API_KEY=sk-..., LLM_MODEL=gpt-4o-mini,
LLM_BASE_URL (OpenAI/OpenRouter/vLLM). Без ключа — MockLLMClient.

## Порог отказа
LLM_THRESHOLD: 0.12 для TF-IDF fallback; после `pip install chromadb sentence-transformers`
и переиндексации — 0.75.

## Миграции
`cd backend; alembic upgrade head` (baseline 0001_init). Приложение также делает create_all при старте.

## Docker
Нужен запущенный Docker Desktop. `docker-compose up --build`. Без Docker — scripts/run_local.bat.
