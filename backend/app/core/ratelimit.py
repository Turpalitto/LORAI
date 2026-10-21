"""Общий лимитер запросов.

Экземпляр должен быть один на приложение: `main` кладёт его в
`app.state.limiter`, роутеры вешают декораторы `@limiter.limit(...)`.
"""
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def rate_limit_handler(request, exc) -> JSONResponse:
    return JSONResponse({"detail": "Слишком много запросов, подождите."},
                        status_code=429)
