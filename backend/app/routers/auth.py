"""Аутентификация: вход с троттлингом неудачных попыток."""
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address

from ..core.deps import client_ip
from ..core.security import make_token, verify_pw
from ..knowledge_base import repository as repo

router = APIRouter(tags=["auth"])


class Login(BaseModel):
    email: str
    password: str


# Троттлинг входа: считаем только неудачные попытки (см. login()).
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_WINDOW = 300.0
_LOGIN_MAX_FAILS = 5


@router.post("/auth/login")
def login(b: Login, request: Request):
    """Вход с троттлингом неудачных попыток.

    Лимит считается только по ОШИБКАМ: 5 промахов за 5 минут на пару
    (IP, email) → 429. Успешные входы не блокируются, поэтому клиника за одним
    NAT-адресом и прогон тестов не упираются в лимит, а скриптовый перебор
    пароля упирается. Раньше на /auth/login лимита не было вовсе — при том что
    /chat был ограничен 30/мин.
    """
    key = f"{get_remote_address(request)}|{(b.email or '').lower()}"
    now = time.monotonic()
    fails = [t for t in _LOGIN_FAILS.get(key, []) if now - t < _LOGIN_WINDOW]
    if len(fails) >= _LOGIN_MAX_FAILS:
        raise HTTPException(429, "Слишком много неудачных попыток входа, попробуйте позже")
    u = repo.get_user(b.email)
    if not u or not u["active"] or not verify_pw(b.password, u["pw_hash"]):
        fails.append(now)
        _LOGIN_FAILS[key] = fails
        if len(_LOGIN_FAILS) > 1000:  # не даём словарю расти бесконечно
            for k in [k for k, v in _LOGIN_FAILS.items() if not v or now - v[-1] > _LOGIN_WINDOW]:
                _LOGIN_FAILS.pop(k, None)
        repo.audit(b.email, "auth.login_failed", target=b.email, ip=client_ip(request))
        raise HTTPException(401, "Неверный логин/пароль")
    _LOGIN_FAILS.pop(key, None)
    repo.touch_login(u["email"])
    repo.audit(u["email"], "auth.login", target=u["email"], ip=client_ip(request))
    return {"token": make_token(u["email"], u["role"]), "role": u["role"]}
