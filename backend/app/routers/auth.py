"""Аутентификация: вход с троттлингом неудачных попыток."""
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from ..core.deps import client_ip, resolve_client_ip
from ..core.security import make_token, verify_pw
from ..knowledge_base import repository as repo

router = APIRouter(tags=["auth"])


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


# Троттлинг входа: считаем только неудачные попытки (см. login()).
# Два счётчика: по паре (IP, email) — против подбора пароля к одной учётке,
# и по IP — против password spraying, когда скрипт перебирает по одному
# паролю на сотню адресов (прежний лимит этого не видел: у каждой пары
# (IP, email) был свой отдельный счётчик).
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_FAILS_BY_IP: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_WINDOW = 300.0
_LOGIN_MAX_FAILS = 5
_LOGIN_MAX_FAILS_PER_IP = 30


def _recent(store: dict[str, list[float]], key: str, now: float) -> list[float]:
    return [t for t in store.get(key, []) if now - t < _LOGIN_WINDOW]


def _drop_expired(store: dict[str, list[float]], now: float) -> None:
    for k in [k for k, v in store.items() if not v or now - v[-1] > _LOGIN_WINDOW]:
        store.pop(k, None)


def reset_login_throttle() -> None:
    """Сброс счётчиков: нужен тестам и ручной разблокировке админом."""
    with _LOGIN_LOCK:
        _LOGIN_FAILS.clear()
        _LOGIN_FAILS_BY_IP.clear()


@router.post("/auth/login")
def login(b: Login, request: Request):
    """Вход с троттлингом неудачных попыток.

    Лимит считается только по ОШИБКАМ: 5 промахов за 5 минут на пару
    (IP, email) и 30 промахов за 5 минут на IP → 429. Успешные входы не
    блокируются, поэтому клиника за одним NAT-адресом и прогон тестов не
    упираются в лимит, а перебор упирается: и точечный (одна учётка), и
    распылённый (много учёток с одного адреса).
    """
    ip = resolve_client_ip(request)
    key = f"{ip}|{(b.email or '').lower()}"
    now = time.monotonic()
    with _LOGIN_LOCK:
        fails = _recent(_LOGIN_FAILS, key, now)
        fails_ip = _recent(_LOGIN_FAILS_BY_IP, ip, now)
        if len(fails) >= _LOGIN_MAX_FAILS:
            raise HTTPException(429, "Слишком много неудачных попыток входа, попробуйте позже")
        if len(fails_ip) >= _LOGIN_MAX_FAILS_PER_IP:
            raise HTTPException(429, "Слишком много неудачных попыток входа с этого адреса")
    u = repo.get_user(b.email)
    if not u or not u["active"] or not verify_pw(b.password, u["pw_hash"]):
        with _LOGIN_LOCK:
            fails.append(now)
            fails_ip.append(now)
            _LOGIN_FAILS[key] = fails
            _LOGIN_FAILS_BY_IP[ip] = fails_ip
            if len(_LOGIN_FAILS) > 1000:  # не даём словарю расти бесконечно
                _drop_expired(_LOGIN_FAILS, now)
            if len(_LOGIN_FAILS_BY_IP) > 1000:
                _drop_expired(_LOGIN_FAILS_BY_IP, now)
        repo.audit(b.email, "auth.login_failed", target=b.email, ip=client_ip(request))
        raise HTTPException(401, "Неверный логин/пароль")
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(key, None)
    repo.touch_login(u["email"])
    repo.audit(u["email"], "auth.login", target=u["email"], ip=client_ip(request))
    return {"token": make_token(u["email"], u["role"]), "role": u["role"]}
