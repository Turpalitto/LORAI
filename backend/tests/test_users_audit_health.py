"""Учётные записи в БД, журнал действий, разделение health и request-id.

Покрывает то, что до 1.4.0 было невозможно: добавить врача без рестарта,
узнать, кто загрузил протокол, отозвать доступ до истечения токена,
увидеть внутренности сервиса без авторизации.
"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _token(c, email="admin@lorai.local", pw="admin123"):
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


# --- health: публичный статус vs админские детали -------------------------

def test_public_health_has_no_internals():
    c = _client()
    h = c.get("/health")
    assert h.status_code == 200
    body = h.json()
    assert body["ok"] is True and body["status"] == "ok"
    assert body["version"]
    # ни количества документов, ни чанков, ни режима LLM, ни ошибок БД
    for leak in ("documents", "chunks", "llm_mode", "llm_configured", "cache", "db"):
        assert leak not in body, leak


def test_admin_health_requires_admin():
    c = _client()
    assert c.get("/admin/health").status_code == 401
    doc = c.post("/auth/login", json={"email": "doctor@lorai.local",
                                      "password": "doctor123"}).json()["token"]
    assert c.get("/admin/health",
                 headers={"Authorization": "Bearer " + doc}).status_code == 403
    h = c.get("/admin/health", headers=_token(c))
    assert h.status_code == 200 and h.json()["ok"] is True


# --- пользователи: создание, вход, отзыв доступа --------------------------

def test_create_user_and_login_without_restart():
    c = _client()
    h = _token(c)
    email = "new.doc@lorai.local"
    r = c.post("/admin/users", headers=h, json={
        "email": email, "password": "strongpass1", "role": "doctor",
        "full_name": "Новый Врач"})
    assert r.status_code in (201, 400), r.text   # 400 — если прогон повторный
    if r.status_code == 201:
        body = r.json()
        assert body["email"] == email and body["role"] == "doctor"
        assert "pw_hash" not in body and "password" not in body

    login = c.post("/auth/login", json={"email": email, "password": "strongpass1"})
    assert login.status_code == 200 and login.json()["role"] == "doctor"

    # повторное создание — понятная 400, а не 500
    assert c.post("/admin/users", headers=h, json={
        "email": email, "password": "strongpass1"}).status_code == 400


def test_create_user_validates_input():
    c = _client()
    h = _token(c)
    assert c.post("/admin/users", headers=h, json={
        "email": "short@lorai.local", "password": "123"}).status_code == 400
    assert c.post("/admin/users", headers=h, json={
        "email": "bad-role@lorai.local", "password": "strongpass1",
        "role": "superuser"}).status_code == 400
    assert c.post("/admin/users", headers=h, json={
        "email": "no-at-sign", "password": "strongpass1"}).status_code == 400


def test_deactivated_user_loses_access_immediately():
    """Токен живёт 8 часов; отключение учётки должно действовать сразу."""
    c = _client()
    h = _token(c)
    email = "revoked@lorai.local"
    c.post("/admin/users", headers=h, json={"email": email, "password": "strongpass1"})
    tok = c.post("/auth/login", json={"email": email, "password": "strongpass1"}).json()["token"]
    uh = {"Authorization": "Bearer " + tok}
    assert c.get("/favorites", headers=uh).status_code == 200

    assert c.patch(f"/admin/users/{email}", headers=h,
                   json={"active": False}).status_code == 200
    # старый токен больше не работает
    assert c.get("/favorites", headers=uh).status_code == 403
    # и войти заново нельзя
    assert c.post("/auth/login", json={
        "email": email, "password": "strongpass1"}).status_code == 401


def test_cannot_lock_yourself_out():
    c = _client()
    h = _token(c)
    r = c.patch("/admin/users/admin@lorai.local", headers=h, json={"active": False})
    assert r.status_code == 400
    r = c.patch("/admin/users/admin@lorai.local", headers=h, json={"role": "doctor"})
    assert r.status_code == 400


def test_password_change_revokes_old_password_only():
    c = _client()
    h = _token(c)
    email = "pw.change@lorai.local"
    c.post("/admin/users", headers=h, json={"email": email, "password": "oldpass123"})
    assert c.patch(f"/admin/users/{email}", headers=h,
                   json={"password": "newpass123"}).status_code == 200
    assert c.post("/auth/login", json={"email": email, "password": "oldpass123"}).status_code == 401
    assert c.post("/auth/login", json={"email": email, "password": "newpass123"}).status_code == 200


# --- аудит ----------------------------------------------------------------

def test_audit_records_login_upload_and_patch():
    c = _client()
    h = _token(c)
    c.post("/auth/login", json={"email": "nobody-audit@lorai.local",
                                "password": "wrong"})

    up = c.post("/admin/upload-pdf", headers=h,
                files={"f": ("audit-probe.txt", b"Otit H66.9. Amoksicilin 500 mg.",
                             "text/plain")})
    assert up.status_code == 202, up.text
    doc_id = up.json()["document_id"]
    assert c.patch(f"/admin/documents/{doc_id}", headers=h,
                   json={"nosology": "Аудит-тест"}).status_code == 200

    items = c.get("/admin/audit?limit=200", headers=h).json()["items"]
    actions = {i["action"] for i in items}
    assert {"auth.login", "auth.login_failed", "document.upload",
            "document.patch"} <= actions
    assert any(i["action"] == "document.patch" and i["target"] == doc_id for i in items)
    # в журнале нет ни пароля, ни его хеша
    blob = " ".join(i["detail"] for i in items)
    assert "wrong" not in blob and "admin123" not in blob and "pbkdf2" not in blob


def test_audit_is_admin_only_and_filterable():
    c = _client()
    doc = c.post("/auth/login", json={"email": "doctor@lorai.local",
                                      "password": "doctor123"}).json()["token"]
    assert c.get("/admin/audit", headers={"Authorization": "Bearer " + doc}).status_code == 403

    h = _token(c)
    only_login = c.get("/admin/audit?action=auth.login&limit=5", headers=h).json()["items"]
    assert only_login and all(i["action"] == "auth.login" for i in only_login)


# --- request-id -----------------------------------------------------------

def test_request_id_header_and_propagation():
    c = _client()
    r1 = c.get("/health")
    r2 = c.get("/health")
    rid1, rid2 = r1.headers.get("X-Request-ID"), r2.headers.get("X-Request-ID")
    assert rid1 and rid2 and rid1 != rid2

    # валидный клиентский id сохраняется (корреляция с внешним прокси)
    r3 = c.get("/health", headers={"X-Request-ID": "edge-abc-123"})
    assert r3.headers["X-Request-ID"] == "edge-abc-123"


def test_request_id_rejects_injection():
    from app.core.logging import sanitize_request_id
    assert sanitize_request_id("ok-123_Abc") == "ok-123_Abc"
    bad = sanitize_request_id("x\nFAKE LOG LINE")
    assert "\n" not in bad and bad != "x\nFAKE LOG LINE"
    assert sanitize_request_id("x" * 200) != "x" * 200


# --- устойчивость записи индекса и фоновых задач --------------------------

def test_atomic_pickle_survives_concurrent_writes(tmp_path):
    """Общий `<path>.tmp` при двух параллельных сохранениях давал ENOENT:
    второй rename не находил файл. Теперь temp уникален, файл всегда валиден."""
    import pickle
    from concurrent.futures import ThreadPoolExecutor

    from app.knowledge_base.vector_store import _atomic_pickle

    path = str(tmp_path / "index.pkl")

    def writer(i):
        for _ in range(15):
            _atomic_pickle(path, {"writer": i, "payload": "x" * 500})

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(writer, range(8)))

    with open(path, "rb") as fh:
        obj = pickle.load(fh)
    assert "writer" in obj
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_upload_lock_is_per_document():
    from app.main import _doc_lock
    assert _doc_lock("doc-a") is _doc_lock("doc-a")
    assert _doc_lock("doc-a") is not _doc_lock("doc-b")


# --- ретенция -------------------------------------------------------------

def test_retention_purges_only_old_rows():
    from sqlalchemy.orm import Session

    from app.knowledge_base import repository as repo
    from app.knowledge_base.models import AuditLog, QueryLog

    old = datetime.utcnow() - timedelta(days=120)
    old_audit = datetime.utcnow() - timedelta(days=400)
    with Session(repo.eng) as s:
        s.add(QueryLog(query="старый запрос", intent="", refused=False,
                       user="retention-probe", created_at=old))
        s.add(QueryLog(query="свежий запрос", intent="", refused=False,
                       user="retention-probe", created_at=datetime.utcnow()))
        s.add(AuditLog(user="retention-probe", action="test.old", created_at=old_audit))
        s.commit()

    assert repo.purge_old_queries(90) >= 1
    assert repo.purge_old_audit(365) >= 1

    with Session(repo.eng) as s:
        left = [r.query for r in s.query(QueryLog).filter_by(user="retention-probe")]
        assert left == ["свежий запрос"]
        assert s.query(AuditLog).filter_by(action="test.old").count() == 0
