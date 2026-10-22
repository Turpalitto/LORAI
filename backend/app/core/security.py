from datetime import datetime, timedelta
import warnings

from jose import jwt
from passlib.context import CryptContext
from .config import settings

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

_DEFAULT_SECRET = "change-me-in-production-please"


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


def check_production_settings() -> None:
    """Fail-fast для production: дефолтные секреты и слабый пароль админа.

    Проверяется на старте приложения, а не при первом входе: иначе установка с
    `admin123` живёт до первой попытки логина, а это уже рабочий контур.
    В development проверка ничего не делает — иначе ломается первичный сид
    администратора и прогон тестов.
    """
    if settings.LORAI_ENV.lower() not in ("prod", "production"):
        return
    problems = []
    if settings.JWT_SECRET == _DEFAULT_SECRET:
        problems.append("JWT_SECRET оставлен дефолтным")
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
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": sub, "role": role, "exp": exp}, _secret(), algorithm=settings.JWT_ALGORITHM)


def decode_token(t: str) -> dict:
    return jwt.decode(t, _secret(), algorithms=[settings.JWT_ALGORITHM])
