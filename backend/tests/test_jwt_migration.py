"""Переход с python-jose на PyJWT (LORAI 1.10.0).

python-jose 3.3.0 несёт CVE-2024-33663 (algorithm confusion: подмена `alg`
в заголовке) и CVE-2024-33664 (JWE с большим числом итераций — DoS).
Библиотека заброшена, поэтому замена, а не «обновить версию».

Токены, выданные python-jose, — обычный JWT HS256 с тем же секретом, поэтому
PyJWT их принимает: разлогинивать врачей при выкатке не нужно. Тест
`test_legacy_python_jose_token_still_valid` держит это свойство явно, с
токеном, выпущенным старой библиотекой до её удаления из зависимостей.
"""
import base64
import json
import time
import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import settings
from app.core.security import TokenExpired, decode_token, make_token

# Секрет, которым подписан «легаси»-токен ниже. Тест подменяет настройку,
# чтобы не зависеть от `.env` разработчика.
LEGACY_SECRET = "legacy-migration-secret-for-tests-0123456789"

# Выпущен python-jose 3.3.0 (HS256), срок — 2036 год. Если этот тест упадёт,
# значит выкатка 1.10.0 разлогинит всех, у кого токен ещё жив.
LEGACY_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJkb2N0b3JAbG9yYWkubG9jYWwiLCJyb2xlIjoiZG9jdG9yIiwiZXhwIjoyMTA4MDI1OTA4fQ."
    "T8JxI-_Pe92WcSz2_iuAXODU0f_0k2ECbdWcDXbvS1k"
)


@pytest.fixture
def legacy_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", LEGACY_SECRET)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    return settings


def _b64(obj: dict) -> str:
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# --- совместимость токенов ---

def test_legacy_python_jose_token_still_valid(legacy_settings):
    payload = decode_token(LEGACY_TOKEN)
    assert payload["sub"] == "doctor@lorai.local"
    assert payload["role"] == "doctor"


def test_roundtrip_has_sub_role_exp_iat(legacy_settings):
    payload = decode_token(make_token("doc@x.z", "doctor"))
    assert payload["sub"] == "doc@x.z"
    assert payload["role"] == "doctor"
    # exp и iat — числовые метки времени, а не datetime: так их видят клиенты.
    assert isinstance(payload["exp"], int) and isinstance(payload["iat"], int)
    assert payload["exp"] > payload["iat"]


# --- ужесточения, которых не было при python-jose ---

def test_token_without_exp_rejected(legacy_settings):
    t = pyjwt.encode({"sub": "doc@x.z", "role": "doctor"}, LEGACY_SECRET, algorithm="HS256")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(t)


def test_token_without_sub_rejected(legacy_settings):
    t = pyjwt.encode(
        {"role": "doctor", "exp": int(time.time()) + 600}, LEGACY_SECRET, algorithm="HS256"
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(t)


def test_alg_none_rejected(legacy_settings):
    """Классическая атака alg=none: подпись отсутствует, `alg` в заголовке."""
    t = (
        _b64({"alg": "none", "typ": "JWT"})
        + "."
        + _b64({"sub": "admin@lorai.local", "role": "admin", "exp": int(time.time()) + 600})
        + "."
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(t)


def test_wrong_secret_rejected(legacy_settings):
    # 32+ символа — чтобы PyJWT не писал InsecureKeyLengthWarning и шум не
    # маскировал реальные предупреждения в выводе тестов.
    wrong = "another-secret-that-is-long-enough-0123456789"
    t = pyjwt.encode(
        {"sub": "doc@x.z", "exp": int(time.time()) + 600}, wrong, algorithm="HS256"
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(t)


def test_expired_token_raises_token_expired(legacy_settings):
    t = pyjwt.encode(
        {"sub": "doc@x.z", "exp": int(time.time()) - 60}, LEGACY_SECRET, algorithm="HS256"
    )
    with pytest.raises(TokenExpired):
        decode_token(t)


def test_expired_is_not_a_generic_invalid_token(legacy_settings):
    """`TokenExpired` — отдельный тип: иначе фронтенд не отличит конец сессии."""
    t = pyjwt.encode(
        {"sub": "doc@x.z", "exp": int(time.time()) - 60}, LEGACY_SECRET, algorithm="HS256"
    )
    try:
        decode_token(t)
    except TokenExpired as exc:
        assert not isinstance(exc, pyjwt.InvalidTokenError)
    else:
        pytest.fail("просроченный токен должен бросать TokenExpired")


# --- конфигурация алгоритма ---

def test_non_hmac_algorithm_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "RS256")
    with pytest.raises(RuntimeError):
        make_token("doc@x.z")
    # Проверка на старте не зависит от LORAI_ENV: это ошибка конфигурации.
    monkeypatch.setattr(settings, "LORAI_ENV", "development")
    with pytest.raises(RuntimeError):
        security.check_production_settings()


def test_short_jwt_secret_fails_in_production(monkeypatch):
    """PyJWT сам предупреждает про ключ <32 байт — в production это отказ старта."""
    monkeypatch.setattr(settings, "LORAI_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 20)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "long-enough-password")
    with pytest.raises(RuntimeError) as exc:
        security.check_production_settings()
    assert "JWT_SECRET" in str(exc.value)


# --- поведение API ---

def test_expired_token_gives_human_401(legacy_settings):
    """Не «Неверный токен», а понятное «сессия истекла»."""
    t = pyjwt.encode(
        {"sub": "doc@x.z", "exp": int(time.time()) - 60}, LEGACY_SECRET, algorithm="HS256"
    )
    from app.main import app

    c = TestClient(app)
    r = c.get("/v1/history", headers={"Authorization": "Bearer " + t})
    assert r.status_code == 401
    assert "истёк" in r.json()["detail"]


def test_expired_token_does_not_break_guest_chat(legacy_settings):
    """Публичный чат: просроченный токен = гость, а не 401."""
    from app.core.deps import optional_auth
    t = pyjwt.encode(
        {"sub": "doc@x.z", "exp": int(time.time()) - 60}, LEGACY_SECRET, algorithm="HS256"
    )
    assert optional_auth("Bearer " + t) == {}
