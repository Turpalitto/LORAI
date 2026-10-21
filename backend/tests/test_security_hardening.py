"""Регрессы доступа и изоляции между пользователями (аудит 2026-10-21).

Каждый тест закрывает конкретную дыру, найденную в коде, а не «на всякий
случай»: токен удалённой учётки, отключённый врач в публичном чате, password
spraying, отсутствие границ у `query`/`k`, общий кэш ответов с чужим
session_id и незалогированное попадание в кэш.
"""
import pytest
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _auth(c, email="admin@lorai.local", pw="admin123"):
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def c():
    """Свежий клиент + сброс троттлинга входа между тестами."""
    from app.routers.auth import reset_login_throttle
    reset_login_throttle()
    yield _client()
    reset_login_throttle()


# --------------------------------------------------------------- H10: токен
def test_token_for_deleted_user_is_rejected(c):
    """Токен несуществующей учётки больше не проходит с ролью ИЗ ТОКЕНА.

    Было: `auth()` возвращал payload как есть, если пользователя нет в БД,
    поэтому уволенный сотрудник работал админом до истечения токена.
    """
    from app.core.security import make_token

    h = {"Authorization": "Bearer " + make_token("ghost@example.com", "admin")}
    assert c.get("/admin/health", headers=h).status_code == 401


def test_token_for_deleted_user_is_rejected_on_history(c):
    from app.core.security import make_token

    h = {"Authorization": "Bearer " + make_token("ghost2@example.com", "doctor")}
    assert c.get("/history", headers=h).status_code == 401


# ---------------------------------------------------- H7: отключённый врач
def test_disabled_user_cannot_chat_as_guest(c):
    """Отключённая учётка получает 403, а не тихо превращается в гостя.

    Было: `optional_auth` возвращал {} — врач продолжал спрашивать, просто
    без записи в историю; отзыв доступа не действовал до конца токена.
    """
    from app.core.security import make_token
    from app.knowledge_base import repository as repo

    email = "disabled-doc@lorai.local"
    try:
        repo.create_user(email, "password123", role="doctor")
    except ValueError:
        pass
    repo.update_user(email, {"active": False})
    h = {"Authorization": "Bearer " + make_token(email, "doctor")}
    r = c.post("/chat", json={"query": "отит лечение"}, headers=h)
    assert r.status_code == 403


def test_broken_token_still_means_guest(c):
    """Битый/отсутствующий токен — по-прежнему гость: публичный чат жив."""
    assert c.post("/chat", json={"query": "отит лечение"}).status_code == 200


# ------------------------------------------------------ H9: password spraying
def test_login_spraying_blocked_per_ip(c):
    """Перебор по разным адресам с одного IP упирается в лимит по IP.

    Было: счётчик только по паре (IP, email), поэтому скрипт с одним паролем
    на сотню адресов не видел 429 вообще.
    """
    codes = []
    for i in range(32):
        r = c.post("/auth/login", json={"email": f"spray{i}@example.com",
                                        "password": "wrong-password"})
        codes.append(r.status_code)
    assert 429 in codes, codes
    assert codes.count(401) <= 30


def test_single_account_still_blocked(c):
    codes = [c.post("/auth/login", json={"email": "admin@lorai.local",
                                         "password": "definitely-wrong"}).status_code
             for _ in range(7)]
    assert 429 in codes


# ------------------------------------------------------------ H8: границы входа
def test_chat_rejects_overlong_query(c):
    r = c.post("/chat", json={"query": "а" * 2500})
    assert r.status_code == 422


def test_chat_rejects_out_of_range_k(c):
    assert c.post("/chat", json={"query": "отит", "k": 99}).status_code == 422
    assert c.post("/chat", json={"query": "отит", "k": 0}).status_code == 422


def test_stream_get_rejects_out_of_range_k(c):
    assert c.get("/chat/stream", params={"query": "отит", "k": 99}).status_code == 422


# ------------------------------------------------------------ H6: кэш чата
def test_cache_does_not_leak_session_between_users(c):
    """Кэш ответов разделён по автору, session_id в кэш не кладётся.

    Было: ключ `chat|<query>|<k>|<f>` без пользователя, а в значение попадал
    session_id. Второй врач на тот же вопрос получал `cached: true` и ЧУЖОЙ
    session_id — его следующий короткий вопрос расширялся препаратом из
    диалога первого врача.
    """
    q = "уникальный вопрос про кэш и сессии H66.9 отит"
    h_admin = _auth(c)
    h_doc = _auth(c, "doctor@lorai.local", "doctor123")
    a = c.post("/chat", json={"query": q}, headers=h_admin).json()
    b = c.post("/chat", json={"query": q}, headers=h_doc).json()
    assert a["cached"] is False
    assert b["cached"] is False, "кэш не должен переиспользоваться между врачами"
    assert b["session_id"] != a["session_id"]

    # Повтор тем же врачом — из кэша, но сессия всё равно своя и новая:
    # чужой (и даже своей прошлой) сессией кэш не подменяет контекст.
    a2 = c.post("/chat", json={"query": q}, headers=h_admin).json()
    assert a2["cached"] is True
    assert a2["session_id"] not in (a["session_id"], b["session_id"])
    assert a2["answer"] == a["answer"]


def test_cache_hit_is_logged(c):
    """Попадание в кэш — тоже запрос: он должен попасть в журнал."""
    from app.knowledge_base import repository as repo

    q = "уникальный вопрос про журнал кэша H66.9"
    h = _auth(c, "doctor@lorai.local", "doctor123")
    before = len(repo.get_history(limit=500, user="doctor@lorai.local"))
    c.post("/chat", json={"query": q}, headers=h)
    c.post("/chat", json={"query": q}, headers=h)  # cached
    after = len(repo.get_history(limit=500, user="doctor@lorai.local"))
    assert after - before == 2


# ------------------------------------------------------- H14: мёртвый regex
def test_latin_drug_name_is_detected():
    """`[a-z]{4,}` + кириллические суффиксы не срабатывал никогда."""
    from app.rag.sessions import _DRUG_RX

    assert _DRUG_RX.search("amoxicillin 500 mg")
    assert _DRUG_RX.search("azithromycin")
    assert _DRUG_RX.search("амоксициллином")
