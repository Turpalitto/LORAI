"""Сборка приложения LORAI.

Раньше здесь жили все роуты — 700 строк, и любая правка шла «в один файл».
Теперь `main` отвечает только за приложение: middleware, обработчики ошибок,
CORS и подключение роутеров из `app/routers/`. Логика эндпоинтов — в роутерах,
зависимости — в `core/deps.py`, фоновая обработка загрузок — в `services/`.

Реэкспорты ниже (`_has_pii`, `_LOGIN_FAILS`, `_doc_lock`, `auth`) оставлены
намеренно: на них ссылаются тесты и внешние скрипты.
"""
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .core.config import settings
from .core.deps import admin_only, auth, optional_auth, uid  # noqa: F401 (реэкспорт)
from .core.logging import (get_request_id, log, reset_request_id,
                           sanitize_request_id, set_request_id)
from .core.privacy import has_pii as _has_pii  # noqa: F401 (реэкспорт)
from .core.ratelimit import limiter, rate_limit_handler
from .knowledge_base import repository as repo
from .routers import account, admin, chat, clinical, protocols, system
from .routers import auth as auth_routes
from .routers.auth import _LOGIN_FAILS  # noqa: F401 (реэкспорт для тестов)
from .services.uploads import doc_lock as _doc_lock  # noqa: F401 (реэкспорт)

app = FastAPI(title="LORAI — помощник ЛОР-врача")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# CORS: явный allowlist вместо "*". Origin нативных мобильных клиентов
# отсутствует — такие запросы браузерной политикой не проверяются,
# поэтому список нужен только для web-клиентов (CORS не авторизация: JWT
# по-прежнему обязателен на каждом защищённом эндпоинте).
ALLOWED_ORIGINS = [o.strip() for o in settings.LORAI_ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# Request-id: один id на запрос, в заголовке ответа и в каждой строке лога.
# Путь логируем без query string — в GET /chat/stream там клинический текст.
# Здесь же помечаем устаревшие (неверсионированные) пути: контракт живёт в /v1,
# а старые адреса продолжают работать, чтобы не ломать уже установленные клиенты.
_UNVERSIONED_OK = {"/health", "/docs", "/redoc", "/openapi.json", "/", "/favicon.ico"}


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = sanitize_request_id(request.headers.get("X-Request-ID"))
    token = set_request_id(rid)
    t0 = time.monotonic()
    try:
        response = await call_next(request)
        ms = round((time.monotonic() - t0) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        path = request.url.path
        if not path.startswith("/v1") and path not in _UNVERSIONED_OK:
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = f'</v1{path}>; rel="successor-version"'
        # Логируем ДО сброса контекста, иначе в строке будет [req=-].
        if path != "/health":
            log.info("%s %s -> %s %.1fms", request.method, path,
                     response.status_code, ms)
        return response
    except Exception:
        log.exception("необработанная ошибка: %s %s", request.method, request.url.path)
        raise
    finally:
        reset_request_id(token)


# Необработанное исключение наружу отдаём без трейсбека и текста ошибки:
# раньше FastAPI возвращал "Internal Server Error" без возможности связать
# ответ с записью в логе. В тестах обработчик не ставим — пусть падает
# громко с трейсбеком, иначе отладка превращается в угадывание.
if os.getenv("LORAI_TESTING") != "1":
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("необработанная ошибка: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": "Внутренняя ошибка сервера", "request_id": get_request_id()})

# Учётки живут в таблице `users` (миграция 0004). env используется только для
# первичного сида: раньше USERS собирался из env при каждом старте, поэтому
# добавить врача можно было лишь правкой .env и рестартом, а смена пароля
# откатывалась при следующем деплое.
BOOTSTRAPPED_USERS = repo.DEFAULT_USERS_CREATED

# Политика хранения: тексты клинических запросов и журнал не хранятся вечно.
# В тестах не чистим — БД и так временная, а прогон не должен зависеть от даты.
if os.getenv("LORAI_TESTING") != "1":
    PURGED_ON_START = {
        "queries": repo.purge_old_queries(settings.QUERY_RETENTION_DAYS),
        "audit": repo.purge_old_audit(settings.AUDIT_RETENTION_DAYS),
    }

API_ROUTERS = (system.router, auth_routes.router, chat.router, account.router,
               protocols.router, clinical.router, admin.router)

# Версионирование контракта. `/v1` — канонический путь и единственный, что
# попадает в OpenAPI. Пути без префикса продолжают работать (мобильный клиент,
# скрипты, закладки), но помечаются Deprecation + Link на /v1 и в схему не
# включаются: новый клиент не должен их видеть.
for _r in API_ROUTERS:
    app.include_router(_r, prefix="/v1")
    app.include_router(_r, include_in_schema=False)
