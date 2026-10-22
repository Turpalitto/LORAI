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
  auth.py               /auth/login (троттлинг неудачных попыток; logout — клиентский,
                        серверный отзыв через active=0 в таблице users)
  system.py             /health (ok/degraded + версия, без внутренностей)
  chat.py               /chat, /chat/stream (SSE, GET и POST)
  account.py            /history, /feedback, /favorites (+ DELETE /favorites/{id})
  protocols.py          /protocols, /protocols/{id}, /protocols/{id}/related, /search-protocol,
                        /checklist/{id}, /templates/{kind}/{id}, /referral-check, /contradictions
  clinical.py           /dosage, /diff-diagnosis, /drug-check, /red-flags,
                        /calculators/*, /regimen/parse, /regimen/validate
  admin.py              /admin/*       документы, загрузка PDF, пользователи, аудит
services/
  uploads.py            _process_upload + per-file/per-doc блокировки
clinical/               normalizer.py + validator.py + data/{drugs,routes,units}.json (из antibio-calc)
ingestion/              pdf_loader → table_parser → icd10 → llm_structurer → pipeline
knowledge_base/         SQLAlchemy (Document, QueryLog, User, AuditLog) + VectorStore
rag/                    intent → retrieval top-k (маршрутизация по разделу и нозологии)
                        → [reranker] → threshold → prompt → generator → анти-галлюцинация
```

Версионирование: роутеры монтируются дважды — `/v1/...` (канонический путь, попадает
в OpenAPI) и без префикса (совместимость, помечен `Deprecation` + `Link` на `/v1`,
из схемы скрыт). `/health` — вне версий, это операционный эндпоинт.

Маршрутизация: `retriever.section_hint` выбирает раздел протокола (лечение,
диагностика, профилактика…), `retriever.nosology_hint` — сам протокол по тексту
вопроса. Оба дают множитель к ранжированию (`SECTION_BOOST`, `NOSOLOGY_BOOST`), не
меняя `score`. Если нозология не распознана однозначно, буст не применяется —
неверный протокол хуже отсутствия подсказки (см. `docs/RETRIEVAL_EVAL.md` §11).

Реранкер (`rag/reranker.py`) выключен по умолчанию: включается `RERANK_BACKEND=cross`
после замера на hold-out (см. `docs/RETRIEVAL_EVAL.md` §реранкер). Он меняет только
порядок, `score` остаётся честным косинусом — иначе врёт порог отказа.

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
