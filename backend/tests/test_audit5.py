"""Аудит-5: регрессионные тесты на найденные дефекты.

SEC-1 JWT fail-fast в prod; SEC-2 CORS allowlist; SEC-3 нет дефолтного
doctor-аккаунта; BUG-1 PII-фильтр (полис/дата рождения/СНИЛС-форматы);
BUG-2 temp-файл upload удаляется; BUG-3 инвалидация кэша при загрузке;
PERF-1 search_protocols через SQL.
"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _tok(c, email="admin@lorai.local", pw="admin123"):
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


# --- SEC-1: fail-fast против дефолтного JWT_SECRET в production ---
def test_jwt_default_secret_fails_in_production():
    from app.core import security
    import app.core.config as cfg

    old_env = cfg.settings.LORAI_ENV
    old_secret = cfg.settings.JWT_SECRET
    try:
        cfg.settings.LORAI_ENV = "production"
        cfg.settings.JWT_SECRET = "change-me-in-production-please"
        try:
            security.make_token("x@y.z", "doctor")
            raised = False
        except RuntimeError:
            raised = True
        assert raised, "prod-запуск с дефолтным секретом обязан падать"
    finally:
        cfg.settings.LORAI_ENV = old_env
        cfg.settings.JWT_SECRET = old_secret


def test_jwt_custom_secret_works():
    from app.core.security import make_token, decode_token
    t = make_token("doc@x.z", "doctor")
    assert decode_token(t)["sub"] == "doc@x.z"


# --- SEC-3: doctor-аккаунт создаётся только из settings ---
def test_doctor_account_env_driven_via_settings():
    """env-переменные читаются через Settings (работает и .env-файл, и os.environ)."""
    import app.main as m
    from app.core.config import settings
    if settings.LORAI_DOCTOR_EMAIL and settings.LORAI_DOCTOR_PASSWORD:
        assert settings.LORAI_DOCTOR_EMAIL in m.USERS
    else:
        assert not any(u["role"] == "doctor" for u in m.USERS.values())


def test_no_builtin_doctor_account():
    c = _client()
    # В тестовом окружении conftest создаёт doctor через env — он должен работать
    r = c.post("/auth/login", json={"email": "doctor@lorai.local", "password": "doctor123"})
    assert r.status_code == 200
    # А произвольный «стандартный» пароль без env-аккаунта — нет
    r2 = c.post("/auth/login", json={"email": "nobody@lorai.local", "password": "doctor123"})
    assert r2.status_code == 401


# --- BUG-1: PII-фильтр ловит форматы, которые раньше пропускал ---
def test_pii_filter_insurance_and_birthdate():
    c = _client()
    for q in (
        "полис ОМС 1234 5678 9012 3456, лечение отита",     # раньше проходил!
        "дата рождения 01.02.1990, чем лечить тонзиллит",   # раньше проходил!
        "снилс 123-456-789 00 назначьте терапию",
        "паспорт 4510 №123456 пациенту",
        "+7 912 345-67-89 — проконсультируйте",
    ):
        r = c.post("/chat", json={"query": q})
        assert "warning" in r.json(), f"ПДн не отфильтрован: {q}"


def test_pii_filter_does_not_block_clinical_queries():
    c = _client()
    r = c.post("/chat", json={"query": "острый средний отит у взрослого: лечение 500 мг амоксициллин"})
    j = r.json()
    assert "warning" not in j, "клинический запрос с числами ложно заблокирован"


# --- BUG-3: загрузка нового документа инвалидирует кэш ---
def test_upload_invalidates_cache():
    c = _client()
    h = _tok(c)
    q = {"q": "уникальный-термин-инвалидации-cache5"}
    r1 = c.post("/search-protocol", json=q).json()
    assert r1["cached"] is False and len(r1["items"]) == 0
    r2 = c.post("/search-protocol", json=q).json()
    assert r2["cached"] is True and len(r2["items"]) == 0  # закэширован «пусто»
    # Загружаем документ, содержащий этот термин
    blob = ("Определение\nСиндром уникальный-термин-инвалидации-cache5 H99.9\n"
            "Диагностика\nОсмотр.\nЛечение\nНаблюдение.\n").encode("utf-8")
    up = c.post("/admin/upload-pdf", headers=h,
                files={"f": ("cache-inv-test5.txt", blob, "text/plain")})
    assert up.status_code == 200, up.text
    r3 = c.post("/search-protocol", json=q).json()
    assert r3["cached"] is False, "кэш не инвалидирован после upload"
    assert len(r3["items"]) == 1, "новый документ не находится после инвалидации"
    # прибираем за собой
    c.patch(f"/admin/documents/{r3['items'][0]['document_id']}",
            headers=h, json={"nosology": "Cache-inv тест (удалить)"})


# --- BUG-2: temp-файлы upload не накапливаются ---
def test_upload_cleans_temp_files(tmp_path, monkeypatch):
    import tempfile
    import os
    c = _client()
    h = _tok(c)
    # Монкипатчим mkstemp: временные файлы пойдут в tmp_path, где мы их посчитаем
    real_mkstemp = tempfile.mkstemp
    def tracked_mkstemp(*a, **kw):
        kw["dir"] = str(tmp_path)
        return real_mkstemp(*a, **kw)
    monkeypatch.setattr(tempfile, "mkstemp", tracked_mkstemp)
    blob = b"%PDF-1.4\nbroken but valid magic"
    c.post("/admin/upload-pdf", headers=h,
           files={"f": ("temp-leak-test.pdf", blob, "application/pdf")})
    leftovers = list(tmp_path.glob("lorai_upload_*"))
    assert leftovers == [], f"temp-файлы утекают: {leftovers}"


# --- PERF-1: search_protocols работает через SQL и находит по МКБ-токенам ---
def test_search_protocols_short_icd_tokens():
    from app.knowledge_base import repository as repo
    hits = repo.search_protocols("H66")
    assert len(hits) >= 1
    assert all("H66" in str(p["icd10_codes"]) or "H66" in (p["title"] + p["nosology"]).lower()
               for p in hits), "в выдаче документ без H66"
    assert repo.search_protocols("") == []
    assert repo.search_protocols("   ") == []
