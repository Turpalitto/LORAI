# ADMIN_GUIDE

## Доступ

Первый администратор создаётся из `.env` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) **только
при первом запуске**, когда таблица `users` пуста. Дальше учётки живут в БД:

- Админ-панель → блок «Пользователи и журнал действий»: создать врача, сменить
  роль, отключить, сменить пароль.
- API: `GET/POST /admin/users`, `PATCH /admin/users/{email}`.
- Правка `ADMIN_PASSWORD` в `.env` после первого запуска **ничего не меняет** —
  пароль меняется в панели (или через PATCH).

Отключение учётки действует немедленно: `auth()` сверяет пользователя с БД, а не
только подпись токена. Выданный ранее JWT перестаёт работать (403).

Роль врача: загрузка PDF и админские эндпоинты запрещены (403).

## Журнал действий и хранение

- `GET /admin/audit?limit=100&action=auth.login&actor=...` — входы (успешные и
  неудачные), загрузка/разбор/правка протоколов, управление учётками.
- Пароли и их хеши в журнал не попадают — только факт смены.
- Ретенция: `QUERY_RETENTION_DAYS=90` (тексты запросов), `AUDIT_RETENTION_DAYS=365`.
  Очистка выполняется при старте; вручную — `POST /admin/maintenance/purge`.

## Загрузка новых КР

1. Вариант А (UI): Админ → войти → выбрать PDF → загрузка идёт в `/admin/upload`
   (лимит 50 МБ, проверка `%PDF`). Ответ `202` + `status=processing`, разбор идёт
   в фоне, панель опрашивает `/protocols/{id}`.
2. Вариант Б (CLI): положить PDF в корень или `data/raw_pdfs` → `python scripts/ingest_pdf.py .`
3. Проверка: `GET /admin/documents` с Bearer-токеном; `needs_review=true` →
   проверить вручную.

## Real LLM

В `.env`: `LLM_PROVIDER=openai`, `LLM_API_KEY=sk-...`, `LLM_MODEL=gpt-4o-mini`,
`LLM_BASE_URL` (OpenAI/OpenRouter/vLLM). Без ключа — `MockLLMClient`.

## Порог отказа

`LLM_THRESHOLD`: 0.12 для TF-IDF fallback; после `pip install chromadb sentence-transformers`
и переиндексации — 0.75.

## Миграции

Схему приводит к head само приложение (`app/core/migrations.py` → `alembic upgrade head`).
Вручную: `cd backend && alembic upgrade head`. `create_all` остался только в тестах
(`LORAI_TESTING=1`). БД, созданная старым `create_all`, штампуется на `0002` и
догоняется автоматически.

## Мониторинг

- `GET /health` — публичный: `{ok, status, version}`. Без внутренностей.
- `GET /admin/health` (admin) — документы, чанки, бэкенд поиска, режим LLM, кэш,
  средняя задержка, политика хранения.
- Каждый ответ содержит `X-Request-ID`; тот же id — в каждой строке лога
  (`[req=...]`). При разборе инцидента просите у пользователя этот заголовок.

## Docker

Нужен запущенный Docker Desktop. `docker-compose up --build`. Без Docker —
`scripts/run_local.sh` / `run_local.bat`.
