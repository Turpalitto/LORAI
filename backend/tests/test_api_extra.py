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
def test_out_of_domain_refusal_despite_generic_words():
    # «лечение» есть и в ЛОР-протоколах, но предмет вопроса — чужая специальность
    from app.rag.anti_hallucination import should_refuse
    chunks = [{"score": 0.16, "text": "лечение отита"}, {"score": 0.14, "text": "диагностика"}]
    assert should_refuse(chunks, 0.12, "лечение перелома лучевой кости") is True
    assert should_refuse(chunks, 0.12, "лечение острого среднего отита H66") is False
def test_search_protocol_bypasses_llm():
    c = _client()
    r = c.post("/search-protocol", json={"q": "H66"})
    j = r.json()
    assert j["llm_used"] is False and len(j["items"]) >= 1
    r2 = c.post("/search-protocol", json={"icd10": "H66"})
    assert len(r2.json()["items"]) >= 1
def test_admin_documents_forbidden_for_doctor():
    c = _client()
    tok = c.post("/auth/login", json={"email": "doctor@lorai.local", "password": "doctor123"}).json()["token"]
    r = c.get("/admin/documents", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403
def test_history_requires_auth():
    c = _client()
    assert c.get("/history").status_code in (401, 422, 403)
def test_upload_pdf_alias_and_dedup():
    c = _client()
    tok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]
    h = {"Authorization": "Bearer " + tok}
    n0 = len(c.get("/admin/documents", headers=h).json()["items"])
    blob = "Определение\nОтит H66.9\nДиагностика\nОтоскопия\nЛечение\nАмоксициллин 500 мг\n".encode("utf-8")
    import time
    fname = f"dedup_audit_{int(time.time()*1000)}.txt"
    r1 = c.post("/admin/upload-pdf", headers=h, files={"f": (fname, blob, "text/plain")})
    assert r1.status_code == 200
    r2 = c.post("/admin/upload-pdf", headers=h, files={"f": (fname, blob, "text/plain")})
    assert r2.status_code == 200
    assert r1.json()["document_id"] == r2.json()["document_id"]
    assert r2.json()["duplicate"] is True
    n1 = len(c.get("/admin/documents", headers=h).json()["items"])
    assert n1 == n0 + 1, (n0, n1)
def test_upload_returns_lifecycle_fields_and_searchable():
    """Полный цикл для UI админки: ответ несёт статус/уверенность/нозологию,
    документ сразу находится в поиске."""
    c = _client()
    tok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]
    h = {"Authorization": "Bearer " + tok}
    import time
    fname = f"lifecycle_{int(time.time()*1000)}.txt"
    blob = "Определение\nФарингит J02.9\nДиагностика\nФарингоскопия\nЛечение\nПолоскание\n".encode("utf-8")
    r = c.post("/admin/upload", headers=h, files={"f": (fname, blob, "text/plain")})
    assert r.status_code == 200
    j = r.json()
    assert j["processing_status"] == "processed"
    assert j["confidence"] in ("high", "medium", "low")
    assert "needs_review" in j and "document_id" in j
    items = c.post("/search-protocol", json={"q": "J02"}).json()["items"]
    assert any(i["document_id"] == j["document_id"] for i in items)
def test_upload_broken_pdf_rejected_cleanly():
    c = _client()
    tok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]
    r = c.post("/admin/upload-pdf", headers={"Authorization": "Bearer " + tok},
               files={"f": ("broken.pdf", b"%PDF-1.4 \x00 broken binary \xff\xfe", "application/pdf")})
    # либо чистая 400, либо needs_review — но не 500
    assert r.status_code in (200, 400)
def test_dosage_pediatric_and_cap():
    c = _client()
    r = c.post("/dosage", json={"weight_kg": 12, "mg_per_kg": 40})
    assert r.json()["single_dose_mg"] == 480.0
    r = c.post("/dosage", json={"weight_kg": 100, "mg_per_kg": 40, "max_mg": 3000})
    assert r.json()["single_dose_mg"] == 3000.0
def test_icd_no_vitamin_false_positive():
    from app.ingestion.icd10_extractor import extract_icd10
    assert "B12" not in extract_icd10("назначить витамин B12")
    assert "H66.9" in extract_icd10("Диагноз H66.9")
    # Код АТХ и supplement-страницы библиографии — не МКБ
    assert "D08" not in extract_icd10("антисептиков (Код АТХ: D08) пациентам")
    assert "D08AJ" not in "".join(extract_icd10("препарат D08AJ хлоргексидин"))
    assert "S55" not in extract_icd10("Eur Respir J 2011;38(S55):4286")
    assert "S79" not in extract_icd10("Med Sci Sports Exerc. 2007;39(5):S79.")
    assert "S55" not in extract_icd10("Otolaryngol Head Neck Surg 2020;162(2_suppl):S1-S55.")
    assert "S22" not in extract_icd10("Int Forum Allergy Rhinol. 2016; 6 Suppl 1:S22-209.")
    assert "S74" not in extract_icd10("Nov;73 Suppl 2(Suppl 2):S74-S81.")
    assert "E10" not in extract_icd10("Ear Nose Throat J. 2013;92(4-5):E10-2.")
    assert "N02" not in extract_icd10("анальгетиков (Код АТХ: N02), разрешённых")
    assert "N06" not in extract_icd10("психоаналептиков (АТХ-N06 Психоаналептики)")
    assert "R06" not in extract_icd10("средства (R06: Антигистаминные средства)")
    assert "A23.25" not in extract_icd10("подбор слухового аппарата A23.25.001)")
    # а настоящие коды обязаны находиться
    for good in ["H66.9", "J01.0", "S02.2", "B00.1", "R04.1", "A46"]:
        assert good in extract_icd10(f"Диагноз {good} подтверждён")
def test_empty_file_does_not_crash(tmp_path):
    from app.ingestion.pipeline import process_pdf
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    doc = process_pdf(str(f), title="empty")
    assert doc["needs_manual_review"] is True
def test_admin_patch_low_confidence():
    c = _client()
    tok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]
    h = {"Authorization": "Bearer " + tok}
    docs = c.get("/admin/documents", headers=h).json()["items"]
    did = docs[0]["document_id"]
    r = c.patch(f"/admin/documents/{did}", headers=h, json={"nosology": "Отит тестовый", "needs_review": True})
    assert r.status_code == 200 and r.json()["nosology"] == "Отит тестовый"
    # врач не может править
    dtok = c.post("/auth/login", json={"email": "doctor@lorai.local", "password": "doctor123"}).json()["token"]
    r2 = c.patch(f"/admin/documents/{did}", headers={"Authorization": "Bearer " + dtok}, json={"nosology": "X"})
    assert r2.status_code == 403
    # вернуть как было
    c.patch(f"/admin/documents/{did}", headers=h, json={"nosology": docs[0]["nosology"], "needs_review": False})
def test_nonstandard_headings_flagged():
    from app.ingestion.pipeline import process_pdf
    import tempfile
    p = tempfile.mktemp(suffix=".txt")
    open(p, "w", encoding="utf-8").write("Случай из практики\nПациент жалуется на ухо\n" + "текст " * 200)
    doc = process_pdf(p, title="Странный документ")
    # ни одной секции не распознано и нет МКБ → ручная проверка, а не тихая потеря
    assert doc["needs_manual_review"] is True
