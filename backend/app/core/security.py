from datetime import datetime, timedelta, timezone
import warnings

import jwt
from jwt import ExpiredSignatureError
from passlib.context import CryptContext
from .config import settings

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

_DEFAULT_SECRET = "change-me-in-production-please"

# Разрешены только HMAC-алгоритмы: с асимметричными ключами (RS*/ES*) секрет
# из `.env` перестаёт быть секретом подписи, и проверка «подписано нашим
# ключом» теряет смысл. Список фиксирован, а не берётся из заголовка токена.
_ALLOWED_ALGORITHMS = ("HS256", "HS384", "HS512")


class TokenExpired(Exception):
    """Токен просрочен.

    Отдельный тип, чтобы роутеры могли отличить «истёк срок» (нужно войти
    заново) от «токен битый/подделан» (нужно разбираться). Раньше оба случая
    давали одинаковый 401 «Неверный токен», и врач не понимал, что сессия
    просто закончилась.
    """


def _algorithm() -> str:
    alg = (settings.JWT_ALGORITHM or "").upper()
    if alg not in _ALLOWED_ALGORITHMS:
        raise RuntimeError(
            f"JWT_ALGORITHM={settings.JWT_ALGORITHM!r} не поддерживается: "
            f"допустимы только {', '.join(_ALLOWED_ALGORITHMS)}."
        )
    return alg


def _secret() -> str:
    """Защита от эксплуатации дефолтного секрета: в production запуск с
    JWT_SECRET из коробки запрещён (fail-fast), в dev — предупреждение."""
    if settings.JWT_SECRET == _DEFAULT_SECRET:
        if settings.LORAI_ENV.lower() in ("prod", "production"):
            raise RuntimeError(
                "JWT_SECRET оставлен дефолтным — запуск в production запрещён. "
                "Задайте JWT_SECRET в .env (см. .env.example)."
            )
        warnings.warn("JWT_SECRET дефолтный — только для разработки!", stacklevel=2)
    return settings.JWT_SECRET


_DEFAULT_ADMIN_PASSWORD = "admin123"
_MIN_ADMIN_PASSWORD = 10
# HS256 с коротким ключом подбирается перебором офлайн: PyJWT на таком ключе
# сам пишет InsecureKeyLengthWarning (RFC 7518 §3.2 — минимум 32 байта).
_MIN_JWT_SECRET = 32


def check_production_settings() -> None:
    """Fail-fast для production: дефолтные секреты и слабый пароль админа.

    Проверяется на старте приложения, а не при первом входе: иначе установка с
    `admin123` живёт до первой попытки логина, а это уже рабочий контур.
    В development проверка ничего не делает — иначе ломается первичный сид
    администратора и прогон тестов. Алгоритм подписи проверяется всегда:
    неверное значение — это ошибка конфигурации, а не окружения.
    """
    _algorithm()
    if settings.LORAI_ENV.lower() not in ("prod", "production"):
        return
    problems = []
    if settings.JWT_SECRET == _DEFAULT_SECRET:
        problems.append("JWT_SECRET оставлен дефолтным")
    elif len(settings.JWT_SECRET) < _MIN_JWT_SECRET:
        problems.append(
            f"JWT_SECRET короче {_MIN_JWT_SECRET} символов — HS256 подбирается перебором"
        )
    if settings.ADMIN_PASSWORD == _DEFAULT_ADMIN_PASSWORD:
        problems.append("ADMIN_PASSWORD оставлен дефолтным (admin123)")
    elif len(settings.ADMIN_PASSWORD) < _MIN_ADMIN_PASSWORD:
        problems.append(f"ADMIN_PASSWORD короче {_MIN_ADMIN_PASSWORD} символов")
    if problems:
        raise RuntimeError(
            "Запуск в production запрещён: " + "; ".join(problems)
            + ". Задайте значения в .env (см. .env.example)."
        )


def hash_pw(p: str) -> str: return pwd.hash(p)


def verify_pw(p: str, h: str) -> bool: return pwd.verify(p, h)


def make_token(sub: str, role: str = "doctor") -> str:
    """Токен доступа: `sub`, `role`, `exp` (обязателен при проверке) и `iat`.

    `iat` добавлен вместе с переходом на PyJWT: без него нельзя отличить
    «токен выдан до смены пароля» от «выдан после» — понадобится, когда
    появится инвалидация по времени смены пароля.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def decode_token(t: str) -> dict:
    """Проверка подписи и срока. Бросает `TokenExpired` или `InvalidTokenError`.

    `require=["exp", "sub"]` — токен без срока жизни или без субъекта
    отклоняется: иначе подписанный когда-то токен остаётся вечным, а
    `payload["sub"]` приходит `None` и превращается в пустую учётку.
    `algorithms=[...]` передаётся явно — PyJWT не смотрит на `alg` из
    заголовка токена, поэтому `alg=none` и подмена HS256 на RS256 не проходят.
    """
    try:
        return jwt.decode(
            t,
            _secret(),
            algorithms=[_algorithm()],
            options={"require": ["exp", "sub"]},
        )
    except ExpiredSignatureError as exc:
        raise TokenExpired("Срок действия токена истёк") from exc

