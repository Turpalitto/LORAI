# ARCHITECTURE

## Backend (FastAPI, `backend/app/`)

```
main.py                 сборка приложения: middleware, CORS, startup (ensure_schema + purge), роутеры
core/
  config.py             Pydantic Settings (.env)
  logging.py            log(), request-id через contextvars
  deps.py               get_db, current_user / optional_auth / admin_only, _uid
  privacy.py            _has_pii — маскирование ПДн в логах
  ratelimit.py          лимитер логина (5 фейлов / 5 мин на IP+email)
  security.py           JWT (PBKDF2), revoke
  migrations.py         ensure_schema → alembic upgrade head (+ legacy stamp 0002)
routers/
  auth.py               /auth/*        логин, refresh, logout, me
  system.py             /health, /ready, /metrics, /version
  chat.py               /chat, /chat/stream (SSE), /search-protocol
  account.py            /history, /account/*
  protocols.py          /protocols, /protocols/{id} (асинхронная загрузка + polling)
  clinical.py           /dosage, /diff, /checklist, /templates, /referral
  admin.py              /admin/*       документы, загрузка PDF, пользователи, аудит
services/
  uploads.py            _process_upload + per-file/per-doc блокировки
clinical/               normalizer.py + data/{drugs,routes,units}.json (из antibio-calc)
ingestion/              pdf_loader → table_parser → icd10 → llm_structurer → pipeline
knowledge_base/         SQLAlchemy (Document, QueryLog, User, AuditLog) + VectorStore
rag/                    intent → retrieval top-k → threshold → prompt → generator → анти-галлюцинация
```

Поток запроса: `routers/* → rag/generator → knowledge_base (SQL + VectorStore) → LLM → проверка чисел → ответ`.
Загрузка: `routers/protocols|admin → services/uploads._process_upload` (BackgroundTasks) → `ingestion/pipeline` → документ `processing → ready|failed`.

## Хранилища
- БД: SQLite локально / Postgres в docker (`docker-compose.yml`). Схема — Alembic (`0001…0004`).
- Векторы: `./data/vector_store` (Chroma; при отсутствии — TF-IDF fallback), атомарная запись pickled-индекса.

## Frontend (React + Vite, `frontend/`)
`src/pages` (chat, protocols, admin, dashboard) + `api/client.ts` (axios, JWT-интерцептор). Node — см. `.nvmrc` (24).
Сборка: `npm run build` (tsc + vite), тесты: `vitest run`.

## Безопасность
JWT (access + refresh, отзыв токенов) · роли admin/doctor · лимит попыток логина · `_has_pii` в логах ·
health без внутренностей · аудит действий админа (`audit_log`).

## Что добавлено аудитом 2026-10-19
`POST /search-protocol` (только БД), `POST /admin/upload-pdf` (алиас), `PATCH /admin/documents/{id}`,
домен-гейт `has_lor_signal` в `should_refuse`, `/history` и `/admin/documents` под JWT+ролями, дедуп загрузок,
учётки в БД + аудит, ретенция `query_log`/`audit_log`, разбиение `main.py` на роутеры.
