"""Зависимости FastAPI: проверка токена, роль, IP клиента.

Вынесено из `main.py`, чтобы роутеры не тянули друг друга и приложение
оставалось сборкой, а не свалкой эндпоинтов.
"""
from fastapi import Depends, Header, HTTPException, Request
from slowapi.util import get_remote_address

from ..knowledge_base import repository as repo
from .security import TokenExpired, decode_token


def auth(authorization: str = Header(default="")) -> dict:
    """Проверка токена + сверка с БД.

    Роль берётся из БД, а не из токена: иначе понижение в правах или
    отключение учётки не действовало бы до истечения токена (8 часов).
    Токен для несуществующего пользователя отклоняется: раньше он проходил
    с ролью ИЗ ТОКЕНА, то есть уволенный сотрудник (или удалённая учётка)
    продолжал работать админом до истечения токена.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Нет токена")
    try:
        payload = decode_token(authorization[7:])
    except TokenExpired:
        # Сессия закончилась — это не атака и не «битый токен»: фронтенд по
        # этому тексту отправляет врача на повторный вход вместо «неверный токен».
        raise HTTPException(401, "Срок действия сессии истёк — войдите заново")
    except Exception:
        raise HTTPException(401, "Неверный токен")
    u = repo.get_user(payload.get("sub", ""))
    if not u:
        raise HTTPException(401, "Учётная запись не найдена")
    if not u["active"]:
        raise HTTPException(403, "Учётная запись отключена")
    payload["role"] = u["role"]
    return payload


def optional_auth(authorization: str = Header(default="")) -> dict:
    """Мягкая аутентификация для публичных эндпоинтов (/chat, /chat/stream).

    Без токена или с битым токеном — гость (публичный чат). Но если токен
    валиден, а учётки уже нет или она отключена, отвечаем 401/403: иначе
    отключённый врач продолжал спрашивать как гость, и отзыв доступа не
    действовал до истечения токена.
    """
    if not authorization.startswith("Bearer "):
        return {}
    try:
        payload = decode_token(authorization[7:])
    except TokenExpired:
        # Публичный эндпоинт: просроченный токен в localStorage не должен
        # ломать гостевой чат — отвечаем как гостю, без 401.
        return {}
    except Exception:
        return {}
    u = repo.get_user(payload.get("sub", ""))
    if not u:
        raise HTTPException(401, "Учётная запись не найдена")
    if not u["active"]:
        raise HTTPException(403, "Учётная запись отключена")
    payload["role"] = u["role"]
    return payload


def uid(user: dict) -> str:
    """Идентификатор автора для журналов: email или `guest`."""
    return (user or {}).get("sub") or "guest"


def resolve_client_ip(request: Request) -> str:
    """IP клиента с учётом обратного прокси.

    `get_remote_address` возвращает адрес TCP-соединения: за nginx это адрес
    прокси, то есть один и тот же для всех врачей. Тогда лимит 30/мин и IP в
    аудите относятся ко всем сразу. X-Forwarded-For учитываем только при
    `TRUST_PROXY_HEADERS=1` — иначе любой клиент подделает себе IP заголовком.
    """
    from .config import settings

    if settings.TRUST_PROXY_HEADERS:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
    return get_remote_address(request) or ""


def client_ip(request: Request) -> str:
    return resolve_client_ip(request)


def admin_only(user: dict = Depends(auth)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Только админ")
    return user
