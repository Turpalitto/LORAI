import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
def test_honest_refusal_e2e():
    c = _client()
    r = c.post("/chat", json={"query": "лечение перелома лучевой кости со смещением у взрослых?"})
    j = r.json()
    assert j["refused"] is True
    assert "не найдена" in j["answer"]
def test_roles_upload_forbidden_for_doctor():
    c = _client()
    tok = c.post("/auth/login", json={"email": "doctor@lorai.local", "password": "doctor123"}).json()["token"]
    r = c.post("/admin/upload", headers={"Authorization": "Bearer " + tok},
               files={"f": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 403
def test_upload_rejects_non_pdf_magic():
    c = _client()
    tok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]
    r = c.post("/admin/upload", headers={"Authorization": "Bearer " + tok},
               files={"f": ("x.pdf", b"NOT A PDF", "application/pdf")})
    assert r.status_code == 400
def test_dosage_math():
    c = _client()
    r = c.post("/dosage", json={"weight_kg": 20, "mg_per_kg": 40})
    assert r.json()["single_dose_mg"] == 800.0
def test_pii_warning():
    c = _client()
    r = c.post("/chat", json={"query": "Иванова паспорт +79990000000 назначьте лечение"})
    assert "warning" in r.json()
