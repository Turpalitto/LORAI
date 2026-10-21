"""Зависимости FastAPI: проверка токена, роль, IP клиента.

Вынесено из `main.py`, чтобы роутеры не тянули друг друга и приложение
оставалось сборкой, а не свалкой эндпоинтов.
"""
from fastapi import Depends, Header, HTTPException, Request
from slowapi.util import get_remote_address

from ..knowledge_base import repository as repo
from .security import decode_token


def auth(authorization: str = Header(default="")) -> dict:
    """Проверка токена + сверка с БД.

    Роль берётся из БД, а не из токена: иначе понижение в правах или
    отключение учётки не действовало бы до истечения токена (8 часов).
    Токен для несуществующего пользователя (например, выданный до переезда
    учёток в БД) пропускается с ролью из токена — иначе все сессии умерли бы
    при деплое.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Нет токена")
    try:
        payload = decode_token(authorization[7:])
    except Exception:
        raise HTTPException(401, "Неверный токен")
    u = repo.get_user(payload.get("sub", ""))
    if u:
        if not u["active"]:
            raise HTTPException(403, "Учётная запись отключена")
        payload["role"] = u["role"]
    return payload


def optional_auth(authorization: str = Header(default="")) -> dict:
    """Мягкая аутентификация для публичных эндпоинтов (/chat, /chat/stream).

    Токен есть — знаем, кто спросил (нужно для истории запросов); нет, битый
    или учётка отключена — работаем как гость, но автора пишем явно.
    """
    if not authorization.startswith("Bearer "):
        return {}
    try:
        payload = decode_token(authorization[7:])
    except Exception:
        return {}
    u = repo.get_user(payload.get("sub", ""))
    if u:
        if not u["active"]:
            return {}
        payload["role"] = u["role"]
    return payload


def uid(user: dict) -> str:
    """Идентификатор автора для журналов: email или `guest`."""
    return (user or {}).get("sub") or "guest"


def client_ip(request: Request) -> str:
    return get_remote_address(request) or ""


def admin_only(user: dict = Depends(auth)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Только админ")
    return user
