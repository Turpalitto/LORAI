"""Общий лимитер запросов.

Экземпляр должен быть один на приложение: `main` кладёт его в
`app.state.limiter`, роутеры вешают декораторы `@limiter.limit(...)`.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter

from .deps import resolve_client_ip


def _key(request: Request) -> str:
    """Ключ лимита — реальный клиент, а не адрес обратного прокси."""
    return resolve_client_ip(request) or "unknown"


limiter = Limiter(key_func=_key)


def rate_limit_handler(request, exc) -> JSONResponse:
    return JSONResponse({"detail": "Слишком много запросов, подождите."},
                        status_code=429)
